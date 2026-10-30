use super::*;
use search::{Entry, Filter, Hit as SearchHit, Preferences, Scope};

#[derive(Default)]
pub struct SearchUi {
    pub entries: Vec<Entry>,
    pub hits: Vec<SearchHit>,
    pub counts: [usize; 5],
    pub scope: Scope,
    pub prefs: Preferences,
    pub filter: Filter,
    pub preview: String,
    pub note: String,
    pub parsing: bool,
    pub picker: bool,
    pub picker_index: usize,
    pub error: String,
    pub layouts: HashMap<String, Vec<Window>>,
}
impl SearchUi {
    pub fn load() -> Self {
        let path = layout_path();
        let prefs = fs::read(path.with_file_name("search-preferences.json"))
            .ok()
            .and_then(|v| serde_json::from_slice(&v).ok())
            .unwrap_or_default();
        let layouts = fs::read(path.with_file_name("layouts.json"))
            .ok()
            .and_then(|v| serde_json::from_slice(&v).ok())
            .unwrap_or_default();
        let mut s = Self {
            prefs,
            layouts,
            note: "Semantic unavailable: offline; fuzzy + cached DSL active".into(),
            ..Self::default()
        };
        for name in VIEWS {
            s.entries.push(Entry::new(
                format!("panel:{name}"),
                (*name).into(),
                Scope::Panels,
                Value::Null,
            ));
        }
        for name in ["Clear workspace", "Save layout"] {
            s.entries.push(Entry::new(
                format!("panel:{name}"),
                name.into(),
                Scope::Panels,
                Value::Null,
            ));
        }
        for name in s.layouts.keys() {
            s.entries.push(Entry::new(
                format!("layout:{name}"),
                format!("Layout: {name}"),
                Scope::Panels,
                Value::Null,
            ));
        }
        if let Ok(bytes) = fs::read(path.with_file_name("search-cache.json")) {
            if let Ok(value) = serde_json::from_slice::<Value>(&bytes) {
                s.catalogue(&value);
            }
        }
        s
    }
    pub fn catalogue(&mut self, value: &Value) {
        self.entries
            .retain(|e| e.scope != Scope::Items && e.scope != Scope::Docs);
        if let Some(rows) = value["data"].as_array() {
            for r in rows {
                if let (Some(id), Some(name)) = (r["item_id"].as_u64(), r["name"].as_str()) {
                    self.entries.push(Entry::new(
                        format!("item:{id}"),
                        name.into(),
                        Scope::Items,
                        r.clone(),
                    ));
                }
            }
        }
        if let Some(docs) = value["docs"].as_array() {
            for r in docs {
                if let (Some(key), Some(name)) = (r["key"].as_str(), r["name"].as_str()) {
                    self.entries
                        .push(Entry::new(key.into(), name.into(), Scope::Docs, r.clone()));
                }
            }
        }
    }
    pub fn save(&self) {
        let path = layout_path().with_file_name("search-preferences.json");
        if let Some(parent) = path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        if let Ok(v) = serde_json::to_vec(&self.prefs) {
            let _ = fs::write(path.with_extension("tmp"), v);
            let _ = fs::rename(path.with_extension("tmp"), path);
        }
    }
    pub fn rank(&mut self) {
        (self.hits, self.counts) = search::rank(
            &self.entries,
            &self.filter,
            self.scope,
            &self.prefs,
            search::nucleo_score,
        );
        if self.filter.text.is_empty()
            && self.filter.members.is_none()
            && self.filter.comparisons.is_empty()
            && self.filter.sort.is_none()
        {
            // Facets are actual cached market rows; unavailable values never become invented zeros.
            let mut featured = vec![];
            for key in self.prefs.pins.iter().chain(self.prefs.recent.iter()) {
                if let Some(i) = self.entries.iter().position(|e| {
                    &e.key == key && (self.scope == Scope::All || e.scope == self.scope)
                }) {
                    if !featured.iter().any(|h: &SearchHit| h.entry == i) {
                        featured.push(SearchHit {
                            entry: i,
                            score: 1.,
                            target: 0,
                            indices: vec![],
                            reason: if self.prefs.pins.contains(key) {
                                "★ pin"
                            } else {
                                "recent"
                            }
                            .into(),
                            semantic_only: false,
                        });
                    }
                }
            }
            if self.scope == Scope::All || self.scope == Scope::Items {
                for (field, label) in [
                    ("change_pct", "top mover"),
                    ("alch_gap", "highest alch gap"),
                ] {
                    let mut rows: Vec<_> = self
                        .entries
                        .iter()
                        .enumerate()
                        .filter_map(|(i, e)| {
                            (e.scope == Scope::Items)
                                .then(|| e.row[field].as_f64().map(|v| (i, v)))
                                .flatten()
                        })
                        .collect();
                    rows.sort_by(|a, b| b.1.total_cmp(&a.1));
                    for (i, v) in rows.into_iter().take(4) {
                        if !featured.iter().any(|h| h.entry == i) {
                            featured.push(SearchHit {
                                entry: i,
                                score: 0.,
                                target: 0,
                                indices: vec![],
                                reason: format!("{label} {v:+.1}"),
                                semantic_only: false,
                            });
                        }
                    }
                }
            }
            for h in &self.hits {
                if !featured.iter().any(|x| x.entry == h.entry) {
                    featured.push(h.clone());
                }
            }
            featured.truncate(self.filter.limit);
            self.hits = featured;
        }
    }
}
impl App {
    pub fn search_changed(&mut self) {
        let query = self.palette.clone().unwrap_or_default();
        match search::parse(&query) {
            Ok(f) => {
                self.search.filter = f;
                self.search.error.clear();
            }
            Err(e) => {
                self.search.error = e;
                self.search.hits.clear();
                return;
            }
        }
        self.search.preview = serde_json::to_string(&self.search.filter).unwrap_or_default();
        self.search.rank();
        self.palette_index = 0;
        self.search.picker = false;
        self.search.parsing = self.connected && !query.is_empty();
        if self.connected && !query.is_empty() {
            let fuzzy: HashMap<u64, f64> = self
                .search
                .hits
                .iter()
                .filter_map(|h| {
                    self.search.entries[h.entry].row["item_id"]
                        .as_u64()
                        .map(|id| (id, h.score))
                })
                .collect();
            let _ = self.commands.send(net::Command::Search(query, fuzzy));
        } else {
            self.search.note = "Semantic unavailable: offline; fuzzy + cached DSL active".into();
        }
    }
    pub fn search_response(&mut self, query: String, kind: String, value: Value) {
        if self.palette.as_ref() != Some(&query) {
            return;
        }
        if kind == "parse" {
            self.search.parsing = false;
            if let Ok(f) = serde_json::from_value::<Filter>(value["filter"].clone()) {
                if f.validate() {
                    self.search.filter = f;
                    self.search.preview = format!(
                        "{} {}",
                        value["source"].as_str().unwrap_or("dsl"),
                        serde_json::to_string(&self.search.filter).unwrap()
                    );
                    self.search.rank();
                }
            }
            if let Some(note) = value["note"].as_str() {
                self.search.note = note.into();
            }
        } else if kind == "error" {
            self.search.parsing = false;
            self.search.note = "Semantic / LLM unavailable; fuzzy + cached DSL active".into();
        } else {
            self.search.note = value["semantic"]
                .as_str()
                .unwrap_or("Semantic unavailable")
                .into();
            if self.search.scope != Scope::Items && self.search.scope != Scope::All {
                return;
            }
            if let Some(rows) = value["data"].as_array() {
                for r in rows {
                    let Some(id) = r["item_id"].as_u64() else {
                        continue;
                    };
                    let key = format!("item:{id}");
                    if let Some(hit) = self
                        .search
                        .hits
                        .iter_mut()
                        .find(|h| self.search.entries[h.entry].key == key)
                    {
                        if let Some(c) = r["cosine"].as_f64() {
                            hit.score = search::blend(hit.score, Some(c));
                        }
                        if let Some(c) = r["cosine"].as_f64() {
                            hit.reason =
                                format!("{} · cosine {c:.3} / blend {:.3}", hit.reason, hit.score);
                        }
                    } else if r["semantic_only"] == true {
                        if let Some(i) = self.search.entries.iter().position(|e| e.key == key) {
                            if search::evaluate(&self.search.entries[i].row, &self.search.filter) {
                                self.search.hits.push(SearchHit {
                                    entry: i,
                                    score: r["score"].as_f64().unwrap_or(0.),
                                    target: 0,
                                    indices: vec![],
                                    reason: format!(
                                        "semantic-only · cosine {:.3}",
                                        r["cosine"].as_f64().unwrap_or(0.)
                                    ),
                                    semantic_only: true,
                                });
                                self.search.counts[0] += 1;
                                self.search.counts[1] += 1;
                            }
                        }
                    }
                }
                search::sort_hits(
                    &self.search.entries,
                    &mut self.search.hits,
                    &self.search.filter,
                    &self.search.prefs,
                );
            }
        }
    }
    fn open_search_hit(&mut self, chosen: Option<&str>) {
        let Some(hit) = self.search.hits.get(self.palette_index) else {
            return;
        };
        let entry = &self.search.entries[hit.entry];
        let (key, name, scope, row) = (
            entry.key.clone(),
            entry.name.clone(),
            entry.scope,
            entry.row.clone(),
        );
        let kind = scope.name().to_string();
        let view = chosen
            .map(str::to_owned)
            .or_else(|| self.search.prefs.types.get(&kind).cloned())
            .unwrap_or_else(|| "Candlestick chart".into());
        self.search.prefs.select(&key);
        if chosen.is_some() {
            self.search.prefs.types.insert(kind, view.clone());
        }
        self.search.save();
        self.palette = None;
        self.search.picker = false;
        match scope {
            Scope::Items => {
                let id = row["item_id"].as_u64().unwrap();
                self.set_ticker(id);
                self.add(view.clone());
                self.set_ticker(id);
                if let Some(w) = self.windows.last_mut() {
                    if view == "Market table" {
                        w.filter = name;
                    } else if view == "QM" {
                        w.set("ids", serde_json::json!([id]));
                    }
                }
            }
            Scope::Docs => {
                self.add("Doc viewer".into());
                if let Some(w) = self.windows.last_mut() {
                    w.set("title", name);
                    w.set("body", row["body"].clone());
                }
            }
            Scope::Jobs => {
                self.choose_job(row["id"].as_str().unwrap_or("").into());
                self.add("Jobs".into());
            }
            Scope::Panels => {
                if let Some(layout) = key.strip_prefix("layout:") {
                    if let Some(ws) = self.search.layouts.get(layout) {
                        self.windows = ws.clone();
                        self.next_id = self.windows.iter().map(|w| w.id).max().unwrap_or(0) + 1;
                        self.clamp(self.width, self.height + 2);
                    }
                } else if name == "Clear workspace" {
                    self.clear_workspace();
                } else if name == "Save layout" {
                    self.palette = Some("layout save ".into());
                } else {
                    self.action(name);
                }
            }
            Scope::All => {}
        }
        self.save();
    }
    pub fn clear_workspace(&mut self) {
        window::clear_workspace(&mut self.windows, &mut self.closed);
        self.save();
    }
    pub fn search_key(&mut self, code: KeyCode, modifiers: KeyModifiers) {
        if self.search.picker {
            match code {
                KeyCode::Esc => self.search.picker = false,
                KeyCode::Down | KeyCode::Tab => {
                    self.search.picker_index = (self.search.picker_index + 1) % 3
                }
                KeyCode::Up => self.search.picker_index = (self.search.picker_index + 2) % 3,
                KeyCode::Enter => {
                    let view =
                        ["Candlestick chart", "Market table", "QM"][self.search.picker_index];
                    self.open_search_hit(Some(view));
                }
                _ => {}
            }
            return;
        }
        match code {
            KeyCode::Esc => self.palette = None,
            KeyCode::Tab => {
                self.search.scope = self.search.scope.next();
                self.search.rank();
                self.palette_index = 0;
            }
            KeyCode::Down => {
                self.palette_index =
                    (self.palette_index + 1).min(self.search.hits.len().saturating_sub(1))
            }
            KeyCode::Up => self.palette_index = self.palette_index.saturating_sub(1),
            KeyCode::Char('p') if modifiers.contains(KeyModifiers::CONTROL) => {
                if let Some(h) = self.search.hits.get(self.palette_index) {
                    self.search.prefs.pin(&self.search.entries[h.entry].key);
                    self.search.save();
                    self.search.rank();
                }
            }
            KeyCode::Char('e') if modifiers.contains(KeyModifiers::CONTROL) => {
                self.palette = Some(self.search.filter.dsl());
                self.search_changed();
            }
            KeyCode::Enter => {
                if modifiers.contains(KeyModifiers::CONTROL)
                    && self
                        .search
                        .hits
                        .get(self.palette_index)
                        .is_some_and(|h| self.search.entries[h.entry].scope == Scope::Items)
                {
                    self.search.picker = true;
                    self.search.picker_index = 0;
                    return;
                }
                let raw = self.palette.clone().unwrap_or_default();
                if let Some(name) = raw
                    .strip_prefix("layout save ")
                    .map(str::trim)
                    .filter(|s| !s.is_empty())
                {
                    self.search
                        .layouts
                        .insert(name.into(), self.windows.clone());
                    let _ = fs::write(
                        layout_path().with_file_name("layouts.json"),
                        serde_json::to_vec(&self.search.layouts).unwrap(),
                    );
                    let key = format!("layout:{name}");
                    self.search.entries.retain(|e| e.key != key);
                    self.search.entries.push(Entry::new(
                        key,
                        format!("Layout: {name}"),
                        Scope::Panels,
                        Value::Null,
                    ));
                    self.palette = None;
                    self.notice = format!("Saved layout {name}");
                } else if raw == "clear workspace" {
                    self.clear_workspace();
                    self.palette = None;
                } else if raw.starts_with("Chat workdir: ") {
                    self.palette = None;
                    self.action(raw);
                } else if self.terminal_command(&raw) {
                    self.palette = None;
                    self.save();
                } else if let Some(value) = raw
                    .strip_prefix("metric ")
                    .map(str::trim)
                    .filter(|s| !s.is_empty())
                {
                    self.metric = value.into();
                    self.palette = None;
                    self.add("Metric series".into());
                } else {
                    self.open_search_hit(None);
                }
            }
            KeyCode::Char(c) if !modifiers.contains(KeyModifiers::CONTROL) => {
                if let Some(q) = self.palette.as_mut() {
                    q.push(c);
                }
                self.search_changed();
            }
            KeyCode::Backspace => {
                if let Some(q) = self.palette.as_mut() {
                    q.pop();
                }
                self.search_changed();
            }
            _ => {}
        }
    }
    pub fn draw_search(&self, f: &mut Frame, area: Rect) {
        let width = 110.min(area.width);
        let height = 29.min(area.height);
        let rect = Rect::new(
            area.width.saturating_sub(width) / 2,
            area.height.saturating_sub(height) / 2,
            width,
            height,
        );
        f.render_widget(Clear, rect);
        let mut lines = vec![
            Line::from(format!(" > {}_", self.palette.as_deref().unwrap_or(""))),
            Line::from(
                Scope::VALUES
                    .iter()
                    .map(|s| {
                        format!(
                            "{}{} ({})",
                            if *s == self.search.scope { "[" } else { "" },
                            s.name(),
                            self.search.counts[*s as usize]
                        ) + if *s == self.search.scope { "]" } else { "" }
                    })
                    .collect::<Vec<_>>()
                    .join("  "),
            ),
            Line::styled(
                if self.search.parsing {
                    "Parsing intent… typing stays local · Ctrl+E edit parsed DSL".into()
                } else {
                    self.search.preview.clone()
                },
                Style::default().fg(Color::Yellow),
            ),
            Line::from(self.search.note.clone()),
            Line::from(
                " Enter open  Ctrl+Enter type  Tab scope  Ctrl+P pin  Ctrl+E edit filter  Esc dismiss",
            ),
        ];
        if !self.search.error.is_empty() {
            lines.push(Line::styled(
                self.search.error.clone(),
                Style::default().fg(Color::Red),
            ));
        }
        lines.insert(
            3,
            Line::styled(
                format!(" Parsed: {}", self.search.filter.dsl()),
                Style::default().fg(ACCENT),
            ),
        );
        for (i, hit) in self
            .search
            .hits
            .iter()
            .enumerate()
            .skip(self.palette_index.saturating_sub(6))
            .take(height.saturating_sub(9) as usize / 2)
        {
            let e = &self.search.entries[hit.entry];
            let selected = i == self.palette_index;
            let mut spans = vec![Span::styled(
                format!(
                    " {} {} ",
                    if selected { "▶" } else { " " },
                    if self.search.prefs.pins.contains(&e.key) {
                        "★"
                    } else {
                        "·"
                    }
                ),
                Style::default().fg(ACCENT),
            )];
            if hit.target == 0 {
                for (n, c) in e.name.chars().enumerate() {
                    spans.push(Span::styled(
                        c.to_string(),
                        Style::default()
                            .fg(if hit.indices.contains(&(n as u32)) {
                                Color::Yellow
                            } else {
                                FG
                            })
                            .add_modifier(if hit.indices.contains(&(n as u32)) {
                                Modifier::BOLD | Modifier::UNDERLINED
                            } else {
                                Modifier::empty()
                            }),
                    ));
                }
            } else {
                spans.push(Span::raw(e.name.clone()));
            }
            spans.push(Span::styled(
                format!("  [{}]", e.scope.name()),
                Style::default().fg(Color::DarkGray),
            ));
            lines.push(Line::from(spans));
            let mut explanation = vec![Span::raw(format!(
                "      {}{}",
                if hit.semantic_only {
                    "semantic-only · "
                } else {
                    ""
                },
                hit.reason
            ))];
            if hit.target > 0 {
                explanation.push(Span::raw(" · matched: "));
                for (n, c) in e.targets[hit.target].label.chars().enumerate().take(90) {
                    explanation.push(Span::styled(
                        c.to_string(),
                        Style::default().fg(if hit.indices.contains(&(n as u32)) {
                            Color::Yellow
                        } else {
                            Color::Gray
                        }),
                    ));
                }
            } else if hit.score > 0. && !hit.semantic_only {
                explanation.push(Span::raw(format!(" · fuzzy {:.3}", hit.score)));
            }
            lines.push(Line::from(explanation));
        }
        f.render_widget(
            Paragraph::new(lines)
                .block(
                    Block::default()
                        .borders(Borders::ALL)
                        .title(" Search / build workspace "),
                )
                .style(Style::default().bg(BG).fg(FG)),
            rect,
        );
        if self.search.picker {
            let r = Rect::new(
                rect.x + 2,
                rect.y + 5,
                rect.width.saturating_sub(4),
                7.min(rect.height),
            );
            f.render_widget(Clear, r);
            let options = ["Chart", "Market table", "Quote monitor"];
            let lines: Vec<_> = options
                .iter()
                .enumerate()
                .map(|(i, s)| {
                    Line::from(format!(
                        " {} {s}",
                        if i == self.search.picker_index {
                            "▶"
                        } else {
                            " "
                        }
                    ))
                })
                .collect();
            f.render_widget(
                Paragraph::new(lines)
                    .block(
                        Block::default()
                            .borders(Borders::ALL)
                            .title(" Open item as… (remembered) "),
                    )
                    .style(Style::default().bg(BG).fg(ACCENT)),
                r,
            );
        }
    }
}
