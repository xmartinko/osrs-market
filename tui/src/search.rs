//! Deterministic, offline search. Nucleo is isolated behind ScoreFn for benchmarking.
use nucleo::{
    Config, Matcher, Utf32String,
    pattern::{AtomKind, CaseMatching, Normalization, Pattern},
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

pub const FIELDS: &[&str] = &[
    "price",
    "alch_gap",
    "spread",
    "spread_pct",
    "volume",
    "buy_limit",
    "capacity",
];
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Comparison {
    pub field: String,
    pub op: String,
    pub value: f64,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Filter {
    pub text: String,
    pub members: Option<bool>,
    pub comparisons: Vec<Comparison>,
    pub sort: Option<String>,
    pub descending: bool,
    pub limit: usize,
}
impl Default for Filter {
    fn default() -> Self {
        Self {
            text: String::new(),
            members: None,
            comparisons: vec![],
            sort: None,
            descending: true,
            limit: 50,
        }
    }
}
impl Filter {
    pub fn validate(&self) -> bool {
        self.limit > 0
            && self.limit <= 200
            && self.text.len() <= 8000
            && self.comparisons.len() <= 30
            && self
                .sort
                .as_ref()
                .is_none_or(|s| FIELDS.contains(&s.as_str()))
            && self.comparisons.iter().all(|c| {
                FIELDS.contains(&c.field.as_str())
                    && [">", ">=", "<", "<=", "="].contains(&c.op.as_str())
                    && c.value.is_finite()
            })
    }
    pub fn dsl(&self) -> String {
        let mut parts = vec![self.text.clone()];
        if let Some(m) = self.members {
            parts.push(if m { "members" } else { "free" }.into());
        }
        for c in &self.comparisons {
            parts.push(format!("{}{}{}", c.field, c.op, c.value));
        }
        if let Some(s) = &self.sort {
            parts.push(format!(
                "sort:{}{s}",
                if self.descending { "" } else { "+" }
            ));
        }
        parts.push(format!("limit:{}", self.limit));
        parts.join(" ").trim().into()
    }
}
fn field(s: &str) -> &str {
    if s == "alch" { "alch_gap" } else { s }
}
pub fn parse(query: &str) -> Result<Filter, String> {
    let mut f = Filter::default();
    let mut text = vec![];
    for token in query.split_whitespace() {
        let low = token.to_lowercase();
        if ["members", "-members", "free"].contains(&low.as_str()) {
            f.members = Some(low == "members");
        } else if let Some(s) = low.strip_prefix("sort:") {
            f.descending = !s.starts_with('+');
            f.sort = Some(field(s.trim_start_matches(['+', '-'])).into());
        } else if let Some(s) = low.strip_prefix("limit:") {
            f.limit = s.parse().map_err(|_| "Invalid limit")?;
        } else if let Some(i) = low.find(['>', '<', '=']) {
            let key = field(&low[..i]);
            if !FIELDS.contains(&key) {
                return Err(format!("Unknown filter field: {key}"));
            }
            let tail = &low[i..];
            let n = if tail.starts_with(">=") || tail.starts_with("<=") {
                2
            } else {
                1
            };
            let op = &tail[..n];
            let raw = &tail[n..];
            let (raw, mul) = if let Some(s) = raw.strip_suffix('k') {
                (s, 1000.)
            } else if let Some(s) = raw.strip_suffix('m') {
                (s, 1_000_000.)
            } else {
                (raw, 1.)
            };
            let value = raw
                .parse::<f64>()
                .map_err(|_| format!("Invalid number: {token}"))?
                * mul;
            f.comparisons.push(Comparison {
                field: key.into(),
                op: op.into(),
                value,
            });
        } else {
            text.push(token);
        }
    }
    f.text = text.join(" ");
    if !f.validate() {
        return Err("Invalid filter, sort or limit (1..200)".into());
    }
    Ok(f)
}
pub fn evaluate(row: &Value, f: &Filter) -> bool {
    if let Some(m) = f.members {
        if row["members"].as_bool() != Some(m) {
            return false;
        }
    }
    f.comparisons.iter().all(|c| {
        row[&c.field].as_f64().is_some_and(|v| {
            v.is_finite()
                && match c.op.as_str() {
                    ">" => v > c.value,
                    ">=" => v >= c.value,
                    "<" => v < c.value,
                    "<=" => v <= c.value,
                    "=" => v == c.value,
                    _ => false,
                }
        })
    })
}
pub fn blend(fuzzy: f64, cosine: Option<f64>) -> f64 {
    0.75 * fuzzy.clamp(0., 1.) + 0.25 * cosine.unwrap_or(0.).clamp(0., 1.)
}
#[derive(Clone, Copy, Debug, Default, PartialEq, Serialize, Deserialize)]
pub enum Scope {
    #[default]
    All,
    Items,
    Panels,
    Docs,
    Jobs,
}
impl Scope {
    pub const VALUES: [Self; 5] = [Self::All, Self::Items, Self::Panels, Self::Docs, Self::Jobs];
    pub fn next(self) -> Self {
        Self::VALUES[(self as usize + 1) % 5]
    }
    pub fn name(self) -> &'static str {
        match self {
            Self::All => "All",
            Self::Items => "Items",
            Self::Panels => "Panels",
            Self::Docs => "Docs",
            Self::Jobs => "Jobs",
        }
    }
}
#[derive(Debug)]
pub struct Target {
    pub label: String,
    text: Utf32String,
    pub weight: f64,
}
#[derive(Debug)]
pub struct Entry {
    pub key: String,
    pub name: String,
    pub scope: Scope,
    pub row: Value,
    pub targets: Vec<Target>,
    words: Vec<Vec<char>>,
}
impl Entry {
    pub fn new(key: String, name: String, scope: Scope, row: Value) -> Self {
        let mut e = Self {
            key,
            name: name.clone(),
            words: name
                .to_lowercase()
                .split_whitespace()
                .map(|s| s.chars().collect())
                .collect(),
            scope,
            row,
            targets: vec![],
        };
        e.target(name, 1.);
        if scope == Scope::Items {
            let acronym: String = e
                .name
                .split_whitespace()
                .filter_map(|w| w.chars().find(|c| c.is_alphanumeric()))
                .collect();
            if acronym.chars().count() > 1 {
                e.target(acronym, 0.92);
            }
            let name = e.name.clone();
            for line in include_str!("../search-aliases.tsv")
                .lines()
                .filter(|l| !l.starts_with('#'))
            {
                if let Some((canonical, aliases)) = line.split_once('|') {
                    if canonical.eq_ignore_ascii_case(&name) {
                        for a in aliases.split(',') {
                            e.target(a.into(), 0.98);
                        }
                    }
                }
            }
            if let Some(examine) = e.row["examine"].as_str().filter(|s| !s.is_empty()) {
                e.target(examine.into(), 0.35);
            }
        }
        e
    }
    fn target(&mut self, label: String, weight: f64) {
        self.targets.push(Target {
            text: Utf32String::from(label.as_str()),
            label,
            weight,
        });
    }
}
#[derive(Clone, Debug)]
pub struct Hit {
    pub entry: usize,
    pub score: f64,
    pub target: usize,
    pub indices: Vec<u32>,
    pub reason: String,
    pub semantic_only: bool,
}
#[derive(Default, Serialize, Deserialize)]
pub struct Preferences {
    pub pins: Vec<String>,
    pub recent: Vec<String>,
    pub types: HashMap<String, String>,
}
impl Preferences {
    pub fn select(&mut self, key: &str) {
        self.recent.retain(|k| k != key);
        self.recent.insert(0, key.into());
        self.recent.truncate(30);
    }
    pub fn pin(&mut self, key: &str) {
        if let Some(i) = self.pins.iter().position(|k| k == key) {
            self.pins.remove(i);
        } else {
            self.pins.push(key.into());
        }
    }
}
pub type ScoreFn = fn(&Pattern, &mut Matcher, &Utf32String) -> Option<u32>;
pub fn nucleo_score(pattern: &Pattern, matcher: &mut Matcher, text: &Utf32String) -> Option<u32> {
    pattern.score(text.slice(..), matcher)
}
/// One edit (including adjacent transposition), with Unicode character boundaries.
#[cfg(test)]
pub fn one_edit(a: &str, b: &str) -> bool {
    let a: Vec<_> = a.chars().collect();
    let b: Vec<_> = b.chars().collect();
    one_edit_chars(&a, &b)
}
fn one_edit_chars(a: &[char], b: &[char]) -> bool {
    if a.len().abs_diff(b.len()) > 1 {
        return false;
    }
    let mut i = 0;
    while i < a.len().min(b.len()) && a[i] == b[i] {
        i += 1;
    }
    if i == a.len().min(b.len()) {
        return true;
    }
    if a.len() == b.len() {
        a[i + 1..] == b[i + 1..]
            || i + 1 < a.len() && a[i] == b[i + 1] && a[i + 1] == b[i] && a[i + 2..] == b[i + 2..]
    } else if a.len() > b.len() {
        a[i + 1..] == b[i..]
    } else {
        a[i..] == b[i + 1..]
    }
}
pub fn rank(
    entries: &[Entry],
    f: &Filter,
    scope: Scope,
    prefs: &Preferences,
    score: ScoreFn,
) -> (Vec<Hit>, [usize; 5]) {
    let pattern = Pattern::new(
        &f.text,
        CaseMatching::Ignore,
        Normalization::Smart,
        AtomKind::Fuzzy,
    );
    let mut matcher = Matcher::new(Config::DEFAULT);
    let mut hits = vec![];
    let mut counts = [0; 5];
    let words: Vec<_> = f
        .text
        .to_lowercase()
        .split_whitespace()
        .map(|w| w.chars().collect::<Vec<_>>())
        .collect();
    let query_len = f.text.chars().count().max(1) as f64;
    let filtered = f.members.is_some() || !f.comparisons.is_empty() || f.sort.is_some();
    for (i, e) in entries.iter().enumerate() {
        if filtered && e.scope != Scope::Items {
            continue;
        }
        if e.scope == Scope::Items && !evaluate(&e.row, f) {
            continue;
        }
        let mut best = None;
        if f.text.is_empty() {
            best = Some((0., 0, String::new()));
        } else {
            for (t, target) in e.targets.iter().enumerate() {
                if best.as_ref().is_some_and(|(v, _, _)| *v >= target.weight) {
                    continue;
                }
                if let Some(raw) = score(&pattern, &mut matcher, &target.text) {
                    let exact = target.label.eq_ignore_ascii_case(&f.text);
                    let value = ((raw as f64 / (query_len * 32.)).min(0.95)
                        + if exact { 0.05 } else { 0. })
                        * target.weight;
                    if best.as_ref().is_none_or(|(v, _, _)| value > *v) {
                        best = Some((value, t, String::new()));
                    }
                }
            }
        }
        if best.is_none() && words.iter().all(|w| w.len() >= 3) && !words.is_empty() {
            if words
                .iter()
                .all(|w| e.words.iter().any(|n| one_edit_chars(w, n)))
            {
                best = Some((0.3, 0, "typo tolerance (one edit per word)".into()));
            }
        }
        let Some((value, target, reason)) = best else {
            continue;
        };
        counts[0] += 1;
        counts[e.scope as usize] += 1;
        if scope != Scope::All && scope != e.scope {
            continue;
        }
        hits.push(Hit {
            entry: i,
            score: value,
            target,
            indices: vec![],
            reason,
            semantic_only: false,
        });
    }
    sort_hits(entries, &mut hits, f, prefs);
    for hit in &mut hits {
        let e = &entries[hit.entry];
        let mut reason = hit.reason.clone();
        if !f.comparisons.is_empty() {
            reason = f
                .comparisons
                .iter()
                .map(|c| {
                    format!(
                        "{} {:+}",
                        if c.field == "alch_gap" {
                            "alch"
                        } else {
                            &c.field
                        },
                        e.row[&c.field].as_f64().unwrap()
                    )
                })
                .collect::<Vec<_>>()
                .join(" · ");
        }
        if let Some(m) = f.members {
            reason = format!("{} {reason}", if m { "members" } else { "free" });
        }
        if let Some(s) = &f.sort {
            reason = format!("{reason} · {s} {}", e.row[s]);
        }
        hit.reason = reason;
        if hit.score > 0. && !hit.reason.starts_with("typo") {
            pattern.indices(
                entries[hit.entry].targets[hit.target].text.slice(..),
                &mut matcher,
                &mut hit.indices,
            );
            hit.indices.sort_unstable();
            hit.indices.dedup();
        }
    }
    (hits, counts)
}

pub fn sort_hits(entries: &[Entry], hits: &mut Vec<Hit>, f: &Filter, prefs: &Preferences) {
    let compare = |a: &Hit, b: &Hit| {
        let ea = &entries[a.entry];
        let eb = &entries[b.entry];
        let priority = |e: &Entry| {
            if prefs.pins.contains(&e.key) {
                1000
            } else if let Some(n) = prefs.recent.iter().position(|k| k == &e.key) {
                100 - n as i32
            } else {
                0
            }
        };
        priority(eb)
            .cmp(&priority(ea))
            .then_with(|| {
                if let Some(s) = &f.sort {
                    let av = ea.row[s].as_f64();
                    let bv = eb.row[s].as_f64();
                    match (av, bv) {
                        (Some(a), Some(b)) => {
                            if f.descending {
                                b.total_cmp(&a)
                            } else {
                                a.total_cmp(&b)
                            }
                        }
                        (Some(_), None) => std::cmp::Ordering::Less,
                        (None, Some(_)) => std::cmp::Ordering::Greater,
                        _ => std::cmp::Ordering::Equal,
                    }
                } else {
                    b.score.total_cmp(&a.score)
                }
            })
            .then_with(|| ea.name.cmp(&eb.name))
    };
    if hits.len() > f.limit {
        hits.select_nth_unstable_by(f.limit, compare);
        hits.truncate(f.limit);
    }
    hits.sort_unstable_by(compare);
}

#[cfg(test)]
mod tests {
    use super::*;
    fn entries() -> Vec<Entry> {
        [
            (1, "Dragon javelin tips"),
            (2, "Armadyl godsword"),
            (3, "Dragon boots"),
            (4, "Épée café"),
        ]
        .iter()
        .map(|(id, n)| {
            Entry::new(
                format!("item:{id}"),
                n.to_string(),
                Scope::Items,
                serde_json::json!({"members":true,"alch_gap":289,"price":1000}),
            )
        })
        .collect()
    }
    #[test]
    fn queries_and_unicode() {
        let e = entries();
        for (q, n) in [
            ("dragon jav tips", "Dragon javelin tips"),
            ("ags", "Armadyl godsword"),
            ("d boots", "Dragon boots"),
            ("drgaon boots", "Dragon boots"),
            ("epee cafe", "Épée café"),
            ("members boots alch>200 sort:alch_gap", "Dragon boots"),
        ] {
            let (hits, _) = rank(
                &e,
                &parse(q).unwrap(),
                Scope::All,
                &Preferences::default(),
                nucleo_score,
            );
            assert_eq!(e[hits[0].entry].name, n, "{q}");
        }
    }
    #[test]
    fn filters_are_closed_and_missing_fails() {
        assert!(parse("shell>1").is_err());
        assert!(parse("price>NaN").is_err());
        assert!(parse("limit:999").is_err());
        assert!(parse("sort:command").is_err());
        let f = parse("free price>=1k volume<2m").unwrap();
        assert_eq!(f.comparisons[0].value, 1000.);
        assert!(!evaluate(
            &serde_json::json!({"members":false,"price":1200}),
            &f
        ));
        assert_eq!(parse(&f.dsl()).unwrap(), f);
    }
    #[test]
    fn pins_recents_and_blending() {
        let e = entries();
        let mut p = Preferences::default();
        p.select("item:3");
        p.pin("item:2");
        let (h, _) = rank(&e, &parse("").unwrap(), Scope::Items, &p, nucleo_score);
        assert_eq!(e[h[0].entry].key, "item:2");
        assert_eq!(e[h[1].entry].key, "item:3");
        assert_eq!(blend(1., Some(0.)), 0.75);
        assert!(one_edit("café", "cafe"));
        assert!(!one_edit("abc", "xyz"));
    }
    #[test]
    fn full_catalogue_latency() {
        let path = std::env::var("OSRS_SEARCH_CATALOGUE").unwrap_or_else(|_| {
            super::super::layout_path()
                .with_file_name("search-cache.json")
                .to_string_lossy()
                .into_owned()
        });
        let Ok(bytes) = std::fs::read(&path) else {
            eprintln!(
                "full catalogue benchmark: no cache at {path}; set OSRS_SEARCH_CATALOGUE (see docs/search.md)"
            );
            return;
        };
        let v: Value = serde_json::from_slice(&bytes).unwrap();
        let rows = v["data"].as_array().unwrap();
        assert!(rows.len() >= 4500, "requires the full item catalogue");
        let e: Vec<_> = rows
            .iter()
            .map(|r| {
                Entry::new(
                    format!("item:{}", r["item_id"]),
                    r["name"].as_str().unwrap().into(),
                    Scope::Items,
                    r.clone(),
                )
            })
            .collect();
        let prefs = Preferences::default();
        let mut times = vec![];
        let mut grouped = std::collections::BTreeMap::<String, Vec<f64>>::new();
        for _ in 0..20 {
            for query in [
                "d",
                "dragon jav tips",
                "ags",
                "d boots",
                "members alch>200 sort:alch_gap",
                "rune",
                "café",
            ] {
                let f = parse(query).unwrap();
                let start = std::time::Instant::now();
                std::hint::black_box(rank(&e, &f, Scope::All, &prefs, nucleo_score));
                let ms = start.elapsed().as_secs_f64() * 1000.;
                times.push(ms);
                grouped.entry(query.into()).or_default().push(ms);
            }
        }
        for (q, mut ts) in grouped {
            ts.sort_by(f64::total_cmp);
            eprintln!(
                "{q}: median {:.3} max {:.3}",
                ts[ts.len() / 2],
                ts.last().unwrap()
            );
        }
        times.sort_by(f64::total_cmp);
        let p99 = times[times.len() * 99 / 100];
        eprintln!(
            "FULL CATALOGUE {} items, {} keystrokes: p50={:0.3}ms p99={p99:0.3}ms max={:0.3}ms",
            rows.len(),
            times.len(),
            times[times.len() / 2],
            times.last().unwrap()
        );
        assert!(p99 < 5., "fuzzy p99 {p99:0.3}ms exceeds 5ms");
    }
}
