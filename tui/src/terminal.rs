//! Terminal interaction and rendering. Every financial/chart transform comes from Python.
use super::*;
use ratatui::widgets::{
    Axis, Chart, Dataset, GraphType,
    canvas::{Canvas, Line as CanvasLine, Rectangle},
};

pub fn link_color(name: &str) -> Color {
    match name {
        "green" => Color::Green,
        "red" => Color::Red,
        "yellow" => Color::Yellow,
        "blue" => Color::LightBlue,
        "magenta" => Color::Magenta,
        _ => ACCENT,
    }
}
fn n(v: &Value) -> f64 {
    v.as_f64().unwrap_or(0.)
}
fn stamp(v: &Value) -> String {
    chrono::DateTime::from_timestamp(v.as_i64().unwrap_or(0), 0)
        .map(|t| t.format("%Y-%m-%d %H:%M").to_string())
        .unwrap_or_default()
}
fn key(w: &Window) -> String {
    format!("terminal:{}", w.id)
}
fn is_panel(view: &str) -> bool {
    ["TAS", "QM", "HCP", "HMAP", "MOST", "EQS", "COMP", "AL"].contains(&view)
}

impl App {
    pub fn sync_terminal(&self) {
        let keys = self
            .windows
            .iter()
            .filter(|w| w.view == "Candlestick chart" || is_panel(&w.view))
            .map(key)
            .collect();
        let _ = self.commands.send(net::Command::TerminalWindows(keys));
        for w in &self.windows {
            let chart = w.view == "Candlestick chart";
            if !chart && !is_panel(&w.view) {
                continue;
            }
            let mut body = if w.options.is_object() {
                w.options.clone()
            } else {
                serde_json::json!({})
            };
            body["item"] = w.item.into();
            body["width"] = w.rect.w.saturating_sub(30).max(1).into();
            let pane_count = body["indicators"]
                .as_array()
                .into_iter()
                .flatten()
                .filter(|v| *v == "RSI" || *v == "MACD")
                .count() as u16;
            body["height"] = chart_height(w.rect.h.saturating_sub(2), pane_count).into();
            if !chart {
                body["kind"] = w.view.clone().into();
                body["linked"] = (!w.link.is_empty()).into();
                body["filter"] = w.filter.clone().into();
                body["sort"] = w.sort.into();
                body["width"] = w.rect.w.saturating_sub(2).max(1).into();
                body["height"] = w.rect.h.saturating_sub(5).max(1).into();
            } else if !w.flag("auto_fit", true) && body["bounds"].is_null() {
                if let Some(v) = self.data.get(&key(w)) {
                    body["bounds"] = v["bounds"].clone();
                }
            }
            let _ = self.commands.send(net::Command::Terminal(
                key(w),
                if chart {
                    "terminal/chart"
                } else {
                    "terminal/panel"
                }
                .into(),
                body,
            ));
        }
    }
    pub fn close_focused(&mut self) {
        if let Some(w) = self.windows.pop() {
            self.closed.push(vec![w]);
        }
    }
    pub fn undo_close(&mut self) {
        if let Some(w) = self.closed.pop() {
            self.windows.extend(w);
        }
    }
    pub fn set_ticker(&mut self, item: u64) {
        self.item = item;
        if let Some(focus) = self.windows.last_mut() {
            let link = focus.link.clone();
            focus.item = item;
            if focus.view == "Candlestick chart" {
                focus.set("offset", 0);
            }
            if !link.is_empty() {
                for w in &mut self.windows {
                    if w.link == link {
                        w.item = item;
                        if w.view == "Candlestick chart" {
                            w.set("offset", 0);
                        }
                    }
                }
            }
        }
    }
    pub fn zoom_chart(&mut self, inward: bool) {
        if !self.windows.is_empty() {
            self.zoom_window(self.windows.len() - 1, inward);
        }
    }
    pub fn zoom_window(&mut self, i: usize, inward: bool) {
        let w = &mut self.windows[i];
        let loaded = self
            .data
            .get(&key(w))
            .map(|v| v["visible_bars"].as_u64().unwrap_or(80))
            .unwrap_or(80);
        let current = w.options["bars"]
            .as_u64()
            .filter(|v| *v > 0)
            .unwrap_or(loaded);
        let bars = if inward {
            (current * 4 / 5).max(5)
        } else {
            (current * 5 / 4 + 1).min(10000)
        };
        w.set("bars", bars);
        self.save();
    }
    pub fn terminal_action(&mut self, action: &str) -> bool {
        if action == "HELP" {
            self.help = true;
            return true;
        }
        if action == "Undo close" {
            self.undo_close();
            return true;
        }
        if is_panel(action) {
            self.add(action.into());
            return true;
        }
        if [
            "G chart",
            "GP chart",
            "GIP intraday",
            "GPO bars",
            "GPL line",
            "GPC candles",
            "GPF area",
        ]
        .contains(&action)
        {
            self.add("Candlestick chart".into());
            if let Some(w) = self.windows.last_mut() {
                w.set(
                    "style",
                    match action {
                        "GPO bars" => "Bars",
                        "GPC candles" => "Candles",
                        "GPF area" => "Area",
                        _ => "Line",
                    },
                );
                if action == "GIP intraday" {
                    w.set("tf", "5m");
                    w.set("range", "5d");
                }
            }
            return true;
        }
        let Some((prefix, value)) = action.split_once(": ") else {
            return false;
        };
        if !["Style", "Scale", "Range", "Resolution", "Indicator", "Link"].contains(&prefix) {
            return false;
        }
        if let Some(w) = self.windows.last_mut() {
            if prefix != "Link"
                && w.view != "Candlestick chart"
                && !(w.view == "COMP" && ["Range", "Resolution"].contains(&prefix))
            {
                self.notice = "Focus a chart to use chart controls".into();
                return true;
            }
            match prefix {
                "Style" => {
                    w.set("style", value);
                    w.set("bounds", Value::Null);
                    w.set("auto_fit", true);
                }
                "Scale" => {
                    let field = match value {
                        "invert" => Some(("invert", false)),
                        "axis left" => Some(("axis_left", false)),
                        "auto fit" => Some(("auto_fit", true)),
                        "lock ratio" => Some(("lock", false)),
                        "price only" => Some(("price_only", true)),
                        _ => None,
                    };
                    if let Some((name, default)) = field {
                        let enabled = !w.flag(name, default);
                        w.set(name, enabled);
                        if name == "invert" {
                            w.set("auto_fit", true);
                        }
                        if name == "lock" && enabled {
                            let ratio = self
                                .data
                                .get(&key(w))
                                .map(|v| v["price_per_bar"].clone())
                                .unwrap_or(Value::Null);
                            w.set("ratio", ratio);
                        }
                        if name == "auto_fit" && !enabled {
                            let b = self
                                .data
                                .get(&key(w))
                                .map(|v| v["bounds"].clone())
                                .unwrap_or(Value::Null);
                            w.set("bounds", b);
                        }
                    } else {
                        w.set("scale", value);
                        w.set("bounds", Value::Null);
                        w.set("auto_fit", true);
                        w.set("lock", false);
                        w.set("ratio", Value::Null);
                    }
                }
                "Range" => {
                    w.set("range", value);
                    if w.view == "Candlestick chart" {
                        w.set("offset", 0);
                        w.set("bars", 0);
                        w.set("date", "");
                    }
                }
                "Resolution" => {
                    w.set("tf", value);
                    if w.view == "Candlestick chart" {
                        w.set("offset", 0);
                        w.set("bars", 0);
                    }
                }
                "Indicator" => {
                    let mut studies = w.options["indicators"]
                        .as_array()
                        .cloned()
                        .unwrap_or_default();
                    if studies.iter().any(|v| v == value) {
                        studies.retain(|v| v != value);
                    } else {
                        studies.push(value.into());
                    }
                    w.set("indicators", Value::Array(studies));
                }
                "Link" => {
                    w.link = if value == "none" {
                        String::new()
                    } else {
                        value.into()
                    };
                }
                _ => {}
            }
        }
        if prefix == "Link" {
            if let Some(item) = self.windows.last().map(|w| w.item) {
                self.set_ticker(item);
            }
        }
        true
    }
    pub fn terminal_command(&mut self, raw: &str) -> bool {
        let raw = raw.trim();
        if raw.contains(": ") && self.terminal_action(raw) {
            return true;
        }
        let alias = match raw {
            "G" | "GP" | "GIP" | "GPO" | "GPL" | "GPC" | "GPF" => Some(match raw {
                "GIP" => "GIP intraday",
                "GPO" => "GPO bars",
                "GPL" => "GPL line",
                "GPC" => "GPC candles",
                "GPF" => "GPF area",
                _ => "G chart",
            }),
            _ => None,
        };
        if let Some(action) = alias {
            return self.terminal_action(action);
        }
        if is_panel(raw) || raw == "HELP" {
            return self.terminal_action(raw);
        }
        if let Some(value) = raw.strip_prefix("item ") {
            if let Ok(item) = value.trim().parse::<u64>() {
                if item > 0 {
                    if !self
                        .windows
                        .last()
                        .is_some_and(|w| w.view == "Candlestick chart" || is_panel(&w.view))
                    {
                        self.add("Candlestick chart".into());
                    }
                    self.set_ticker(item);
                    return true;
                }
            }
            self.notice = "Item ID must be a positive integer".into();
            return true;
        }
        if let Some(date) = raw.strip_prefix("date ") {
            if chrono::NaiveDate::parse_from_str(date, "%Y-%m-%d").is_err() {
                self.notice = "Date requires YYYY-MM-DD".into();
                return true;
            }
            if let Some(w) = self
                .windows
                .last_mut()
                .filter(|w| w.view == "Candlestick chart")
            {
                w.set("date", date);
                w.set("offset", 0);
                w.set("bars", 0);
            }
            return true;
        }
        if let Some(value) = raw.strip_prefix("box ") {
            if let Ok(v) = value.parse::<f64>() {
                if v > 0. && v.is_finite() {
                    if let Some(w) = self
                        .windows
                        .last_mut()
                        .filter(|w| w.view == "Candlestick chart")
                    {
                        w.set("box", v);
                    }
                    return true;
                }
            }
            self.notice = "Box size must be positive".into();
            return true;
        }
        if let Some(value) = raw
            .strip_prefix("watch ")
            .or_else(|| raw.strip_prefix("compare "))
        {
            let parsed: Result<Vec<u64>, _> = value
                .split([',', ' '])
                .filter(|s| !s.is_empty())
                .map(str::parse)
                .collect();
            let Ok(ids) = parsed else {
                self.notice = "Use comma-separated positive item IDs".into();
                return true;
            };
            if ids.is_empty()
                || ids.contains(&0)
                || ids.len() > if raw.starts_with("compare ") { 5 } else { 100 }
            {
                self.notice = "Watch: 1–100 IDs; compare: 1–5 IDs".into();
                return true;
            }
            if raw.starts_with("compare ") && !self.windows.last().is_some_and(|w| w.view == "COMP")
            {
                self.add("COMP".into());
            }
            if raw.starts_with("watch ") && !self.windows.last().is_some_and(|w| w.view == "QM") {
                self.add("QM".into());
            }
            if let Some(w) = self.windows.last_mut() {
                w.set("ids", serde_json::json!(ids));
            }
            return true;
        }
        if let Some(value) = raw.strip_prefix("screen ") {
            if !self.windows.last().is_some_and(|w| w.view == "EQS") {
                self.add("EQS".into());
            }
            let mut opts = serde_json::json!({});
            if value != "reset" {
                for term in value.split_whitespace() {
                    let Some((name, v)) = term.split_once('=') else {
                        self.notice =
                            "screen spread=N volume=N alch=N members=free|members limit=MIN:MAX"
                                .into();
                        return true;
                    };
                    match name {
                        "spread" | "volume" | "alch" => {
                            let Ok(number) = v.parse::<f64>() else {
                                self.notice = "Invalid numeric screen filter".into();
                                return true;
                            };
                            if !number.is_finite() || name == "volume" && number < 0. {
                                self.notice = "Invalid screen value".into();
                                return true;
                            }
                            opts[match name {
                                "spread" => "min_spread",
                                "volume" => "min_volume",
                                _ => "min_alch",
                            }] = number.into();
                        }
                        "members" => {
                            if !["free", "members", "all"].contains(&v) {
                                self.notice = "members=free|members|all".into();
                                return true;
                            }
                            if v != "all" {
                                opts["members"] = (v == "members").into();
                            }
                        }
                        "limit" => {
                            let Some((a, b)) = v.split_once(':') else {
                                self.notice = "limit=MIN:MAX".into();
                                return true;
                            };
                            let (Ok(a), Ok(b)) = (a.parse::<u64>(), b.parse::<u64>()) else {
                                self.notice = "limit=MIN:MAX".into();
                                return true;
                            };
                            if a > b {
                                self.notice = "Limit minimum exceeds maximum".into();
                                return true;
                            }
                            opts["limit_min"] = a.into();
                            opts["limit_max"] = b.into();
                        }
                        _ => {
                            self.notice = format!("Unknown screen filter: {name}");
                            return true;
                        }
                    }
                }
            }
            if let Some(w) = self.windows.last_mut() {
                w.options = opts;
                w.scroll = 0;
            }
            self.notice = "Screen filters applied".into();
            return true;
        }
        if let Some(value) = raw.strip_prefix("alert delete ") {
            if let Ok(id) = value.parse::<u64>() {
                let _ = self.commands.send(net::Command::DeleteAlert(id));
            }
            return true;
        }
        if let Some(value) = raw.strip_prefix("alert ") {
            let parts: Vec<_> = value.split_whitespace().collect();
            if parts.len() == 3
                && ["price", "spread", "alch_gap"].contains(&parts[0])
                && ["above", "below"].contains(&parts[1])
            {
                if let Ok(threshold) = parts[2].parse::<f64>() {
                    if threshold.is_finite() {
                        let item = self.windows.last().map(|w| w.item).unwrap_or(self.item);
                        let id = chrono::Utc::now().timestamp_nanos_opt().unwrap_or(0);
                        let _=self.commands.send(net::Command::Terminal(format!("alert-create:{id}"),"terminal/alerts".into(),
                        serde_json::json!({"item":item,"field":parts[0],"direction":parts[1],"threshold":threshold})));
                        self.notice = format!("Saving alert for {item}");
                        return true;
                    }
                }
            }
            self.notice = "alert price|spread|alch_gap above|below NUMBER".into();
            return true;
        }
        false
    }
    pub fn alert_flash(&self) -> String {
        let recent = self
            .rows("terminal/alerts")
            .into_iter()
            .filter(|r| {
                r["triggered"]
                    .as_f64()
                    .is_some_and(|t| chrono::Utc::now().timestamp() as f64 - t < 60.)
            })
            .count();
        if recent > 0 {
            format!("ALERT: {recent} threshold(s) fired — AL")
        } else {
            String::new()
        }
    }
    pub fn draw_help(&self, f: &mut Frame, area: Rect) {
        let width = 116.min(area.width);
        let height = 41.min(area.height);
        let rect = Rect::new(
            area.width.saturating_sub(width) / 2,
            area.height.saturating_sub(height) / 2,
            width,
            height,
        );
        f.render_widget(Clear, rect);
        let text = "F1 / Esc: dismiss help                         OSRS TERMINAL — SHORTCUTS\n\n` / Ctrl+P / /   Command palette (type aliases or commands; arrows + Enter choose)\nTab / Shift+Tab Cycle windows       click: focus/raise       m: fullscreen\nArrows / Shift+arrows: move         Alt+arrows: grow chosen edge; Ctrl+Alt+arrows: shrink chosen edge\nCtrl+Shift+arrows: snap to edge      Alt+Shift+arrows: resize to edge\nDrag title: move; any edge/corner (2 cells): resize      Ctrl+W / title × / double Esc: close\nCtrl+Z: undo last close             q / Ctrl+C: quit client (jobs continue)\nf: text filter; Enter finish; Esc clear    s: rank/color mode    j/k: scroll/select job
Enter on market/TAS/QM/HCP/MOST/EQS tables: chart selected item and update linked ticker\n\nCHART   C: style picker   S / right click: scale menu   I: studies   R: range\n1: 5m   2: 15m   3: 30m   4: 1h   5: 1d   6: 1w   (no sub-5m data)\nWheel / +/-: time zoom   drag chart: pan   j/k: pan buckets   hover: inspect\nStyles: Candles, Bars, Line, Area, Baseline, Heikin Ashi, Hollow Candles,\n        Renko, Kagi, Point & Figure, Line Break\nScales: linear / percent / indexed / logarithmic; invert, axis left, auto fit, lock ratio
Scale: price only excludes studies from auto-fit bounds. F1 help: j/k or PgUp/PgDn scroll.\nIndicators: SMA20 / EMA20 / BOLL20,2 / RSI14 / MACD12,26,9 / cumulative bucket VWAP\nRanges: 5y / 1y / 6m / 3m / 1m / 5d / 1d (independent of resolution)\n\nPALETTE COMMANDS\nG / GP / GPL: line   GIP: intraday   GPO: bars   GPC: candles   GPF: area\nitem 4151                 Set focused ticker; all same-colour windows follow\nLink: red|green|blue|yellow|magenta|none     Set focused window's link group\ndate 2025-01-15            Jump chart range end to UTC date\nbox 100                   Fixed box size for Renko / Kagi / P&F\nTAS / QM / HCP / HMAP / MOST / EQS / COMP / AL    Open a panel\nwatch 855,561,4151         Choose QM watchlist\ncompare 855,859,4151       Compare up to five items, exact common start = 100\nscreen spread=10 volume=100 alch=0 members=free limit=1:10000\nscreen reset              Clear composable EQS constraints\nalert price above 1000    Alert on focused ticker (price = latest side midpoint)\nalert spread below 10     Net spread threshold; alch_gap also supported\nalert delete 1            Delete saved alert; fired thresholds remain in AL\nmetric net_gp             Open job metric   c in Jobs: cancel selected job\nDataset / Track / Preset / Horizon: configure jobs; Start benchmark|eval|train|backtest\n\nCHAT Enter/i: edit; Enter: send; Alt+Enter/Ctrl+J: newline; Esc: leave input\nArrows/Home/End/Backspace/Delete: edit; Ctrl+X/Ctrl+C: cancel; wheel: transcript\n\nDATA: bucket means, not trade OHLC. Candle family says mean-envelope.\nTAS is aggregated bucket events. MOST has no trade counts. AL stays server-side.";
        f.render_widget(
            Paragraph::new(text)
                .scroll((self.help_scroll, 0))
                .block(
                    Block::default()
                        .borders(Borders::ALL)
                        .title(" HELP — F1/Esc close · j/k scroll "),
                )
                .style(Style::default().bg(BG).fg(FG)),
            rect,
        );
    }
    pub fn terminal_chart(&self, f: &mut Frame, area: Rect, w: &Window) {
        if area.width < 35 || area.height < 14 {
            f.render_widget(Paragraph::new("Enlarge chart to at least 35×14"), area);
            return;
        }
        let Some(v) = self.data.get(&key(w)) else {
            f.render_widget(Paragraph::new("Loading server chart…"), area);
            return;
        };
        let header = format!(
            "{} {} {} · {} · {} · {}",
            w.item,
            w.option("tf", "1d"),
            val(&v["style"]),
            val(&v["scale"]),
            val(&v["provenance"]),
            if v["stale"] == true || !self.connected {
                "STALE"
            } else {
                "LIVE"
            }
        );
        f.render_widget(
            Paragraph::new(header).style(Style::default().fg(ACCENT)),
            Rect::new(area.x, area.y, area.width, 1),
        );
        let countdown = (n(&v["close_at"]) - chrono::Utc::now().timestamp() as f64).max(0.) as u64;
        f.render_widget(
            Paragraph::new(format!(
                "{} last mean {}  range Δ {:.2} ({:.2}%)  visible volume {}  next bucket {:02}:{:02}:{:02}{}",
                if n(&v["delta"]) >= 0. { "▲" } else { "▼" },
                val(&v["last"]["close"]),
                n(&v["delta"]),
                n(&v["change_pct"]),
                val(&v["visible_volume"]),
                countdown / 3600,
                countdown / 60 % 60,
                countdown % 60,
                if v["bucket_historical"] == true {
                    " [historical series]"
                } else {
                    ""
                }
            )),
            Rect::new(area.x, area.y + 1, area.width, 1),
        );
        if let Some(error) = v["error"].as_str() {
            f.render_widget(
                Paragraph::new(error).style(Style::default().fg(Color::Red)),
                Rect::new(area.x, area.y + 2, area.width, 1),
            );
        }
        if v["visible_bars"].as_u64() == Some(0) || v["count"].is_null() {
            f.render_widget(
                Paragraph::new(if let Some(e) = v["error"].as_str() {
                    e.to_string()
                } else {
                    "No observations in this range. Choose another range, resolution or date."
                        .into()
                })
                .style(Style::default().fg(Color::Yellow)),
                Rect::new(area.x, area.y + 3, area.width, 2),
            );
            return;
        }
        let panes = v["panes"].as_array().cloned().unwrap_or_default();
        let pane_h = if panes.is_empty() {
            0
        } else {
            (area.height.saturating_sub(12) / (panes.len() as u16 + 2)).clamp(2, 5)
        };
        let plot_h = area
            .height
            .saturating_sub(10 + pane_h * panes.len() as u16)
            .max(2);
        let left = w.flag("axis_left", false);
        let plot = Rect::new(
            area.x + if left { 28 } else { 0 },
            area.y + 3,
            area.width - 28,
            plot_h,
        );
        let axis_x = if left { area.x } else { plot.right() };
        let bounds = [n(&v["bounds"][0]), n(&v["bounds"][1])];
        let count = n(&v["count"]).max(1.);
        let hovered = self
            .hover
            .filter(|(x, y)| plot.contains(Position::new(*x, *y)))
            .map(|(x, _)| window::chart_index(x, plot.x, plot.width, count as usize));
        if let Some(i) = hovered {
            if let Some(row) = v["cursor"].as_array().and_then(|rows| rows.get(i)) {
                f.render_widget(
                    Paragraph::new(format!(
                        "{} UTC · mean {} · volume {}",
                        stamp(&row["timestamp"]),
                        val(&row["close"]),
                        val(&row["volume"])
                    ))
                    .style(Style::default().fg(Color::Yellow)),
                    Rect::new(area.x, area.y + 2, area.width, 1),
                );
            }
        }
        f.render_widget(
            Canvas::default()
                .background_color(BG)
                .marker(symbols::Marker::Braille)
                .x_bounds([-0.5, count - 0.5])
                .y_bounds(bounds)
                .paint(|ctx| {
                    for i in 0..5 {
                        let y = bounds[0] + (bounds[1] - bounds[0]) * i as f64 / 4.;
                        ctx.draw(&CanvasLine {
                            x1: -0.5,
                            y1: y,
                            x2: count - 0.5,
                            y2: y,
                            color: Color::Rgb(30, 42, 52),
                        });
                    }
                    if let Some(lines) = v["lines"].as_array() {
                        for l in lines {
                            ctx.draw(&CanvasLine {
                                x1: n(&l[0]),
                                y1: n(&l[1]),
                                x2: n(&l[2]),
                                y2: n(&l[3]),
                                color: link_color(l[4].as_str().unwrap_or("")),
                            });
                        }
                    }
                    if let Some(rects) = v["rects"].as_array() {
                        for r in rects {
                            let x = n(&r[0]);
                            let y = n(&r[1]);
                            let h = n(&r[3]).max((bounds[1] - bounds[0]) / 300.);
                            let col = link_color(r[4].as_str().unwrap_or(""));
                            ctx.draw(&Rectangle {
                                x,
                                y,
                                width: n(&r[2]),
                                height: h,
                                color: col,
                            });
                            if r[5] == true {
                                for j in 1..5 {
                                    let xp = x + n(&r[2]) * j as f64 / 5.;
                                    ctx.draw(&CanvasLine {
                                        x1: xp,
                                        y1: y,
                                        x2: xp,
                                        y2: y + h,
                                        color: col,
                                    });
                                }
                            }
                        }
                    }
                    if let Some(glyphs) = v["glyphs"].as_array() {
                        for g in glyphs {
                            ctx.print(
                                n(&g[0]),
                                n(&g[1]),
                                Span::styled(
                                    val(&g[2]),
                                    Style::default().fg(link_color(g[3].as_str().unwrap_or(""))),
                                ),
                            );
                        }
                    }
                    if let Some(i) = hovered {
                        ctx.draw(&CanvasLine {
                            x1: i as f64,
                            y1: bounds[0],
                            x2: i as f64,
                            y2: bounds[1],
                            color: Color::Yellow,
                        });
                    }
                }),
            plot,
        );
        if let Some(ticks) = v["ticks"].as_array() {
            for (i, t) in ticks.iter().enumerate() {
                let y = plot.y + plot.height.saturating_sub(1) * i as u16 / 4;
                f.render_widget(
                    Paragraph::new(val(t)).style(Style::default().fg(Color::DarkGray)),
                    Rect::new(axis_x, y, 27, 1),
                );
            }
        }
        if let Some(labels) = v["labels"].as_array() {
            for l in labels {
                let y = plot.y + (n(&l["row"]) as u16).min(plot.height.saturating_sub(1));
                f.render_widget(
                    Paragraph::new(val(&l["text"])).style(Style::default().fg(Color::Yellow)),
                    Rect::new(axis_x, y, 27, 1),
                );
            }
        }
        let volume = v["volume"].as_array().cloned().unwrap_or_default();
        let maxvol = n(&v["volume_bounds"][1]).max(1.);
        let vol_rect = Rect::new(plot.x, plot.bottom(), plot.width, 2);
        f.render_widget(
            Canvas::default()
                .background_color(BG)
                .x_bounds([-0.5, volume.len().max(1) as f64 - 0.5])
                .y_bounds([0., maxvol])
                .paint(|ctx| {
                    for p in &volume {
                        ctx.draw(&CanvasLine {
                            x1: n(&p[0]),
                            y1: 0.,
                            x2: n(&p[0]),
                            y2: n(&p[1]),
                            color: Color::LightBlue,
                        });
                    }
                }),
            vol_rect,
        );
        let mut y = vol_rect.bottom();
        for pane in &panes {
            let series = pane["points"].as_object();
            let points: Vec<(String, Vec<(f64, f64)>)> = series
                .into_iter()
                .flatten()
                .map(|(name, ps)| {
                    (
                        name.clone(),
                        ps.as_array()
                            .into_iter()
                            .flatten()
                            .map(|p| (n(&p[0]), n(&p[1])))
                            .collect(),
                    )
                })
                .collect();
            let datasets = points
                .iter()
                .enumerate()
                .map(|(i, (name, ps))| {
                    Dataset::default()
                        .name(name.clone())
                        .marker(symbols::Marker::Braille)
                        .graph_type(GraphType::Line)
                        .style(Style::default().fg(if i % 2 == 0 { ACCENT } else { Color::Yellow }))
                        .data(ps)
                })
                .collect();
            let maxx = volume.len().max(2) as f64 - 1.;
            f.render_widget(
                Chart::new(datasets)
                    .block(Block::default().title(val(&pane["name"])))
                    .x_axis(Axis::default().bounds([0., maxx]))
                    .y_axis(Axis::default().bounds([n(&pane["bounds"][0]), n(&pane["bounds"][1])]))
                    .style(Style::default().bg(BG)),
                Rect::new(plot.x, y, plot.width, pane_h),
            );
            y += pane_h;
        }
        f.render_widget(
            Paragraph::new(format!(
                "{} → {} UTC  {}/{} buckets  {}",
                stamp(&v["first"]["timestamp"]),
                stamp(&v["last"]["timestamp"]),
                val(&v["visible_bars"]),
                val(&v["available_bars"]),
                if v["event_axis"] == true {
                    "event axis"
                } else {
                    "bucket axis"
                }
            ))
            .style(Style::default().fg(Color::Gray)),
            Rect::new(area.x, area.bottom() - 3, area.width, 1),
        );
        f.render_widget(
            Paragraph::new(val(&v["source"])).style(Style::default().fg(Color::Gray)),
            Rect::new(area.x, area.bottom() - 2, area.width, 1),
        );
        f.render_widget(
            Paragraph::new(format!(
                "C styles · S scale · I studies · R range · wheel zoom · drag pan · {}",
                val(&v["note"])
            ))
            .style(Style::default().fg(Color::DarkGray)),
            Rect::new(area.x, area.bottom() - 1, area.width, 1),
        );
    }
    pub fn terminal_panel(&self, f: &mut Frame, area: Rect, w: &Window) {
        if area.width < 10 || area.height < 4 {
            return;
        }
        let Some(v) = self.data.get(&key(w)) else {
            f.render_widget(Paragraph::new("Loading server panel…"), area);
            return;
        };
        f.render_widget(
            Paragraph::new(format!(
                "{} · {}",
                if !self.connected || v["stale"] == true {
                    "STALE"
                } else {
                    "LIVE"
                },
                val(&v["basis"])
            ))
            .style(Style::default().fg(ACCENT)),
            Rect::new(area.x, area.y, area.width, 1),
        );
        if let Some(error) = v["error"].as_str() {
            f.render_widget(
                Paragraph::new(error).style(Style::default().fg(Color::Red)),
                Rect::new(area.x, area.y + 1, area.width, 1),
            );
        } else if w.view == "EQS" {
            f.render_widget(
                Paragraph::new(format!(
                    "Filters {} · {} matches",
                    val(&v["filters_label"]),
                    v["data"].as_array().map(|r| r.len()).unwrap_or(0)
                ))
                .style(Style::default().fg(Color::Yellow)),
                Rect::new(area.x, area.y + 1, area.width, 1),
            );
        }
        if w.view == "HMAP" {
            let field = v["color_field"].as_str().unwrap_or("spread");
            if let Some(cells) = v["cells"].as_array() {
                for cell in cells {
                    let item = &cell["item"];
                    let raw = cell[field].as_f64().or_else(|| item[field].as_f64());
                    let bg = match raw {
                        None => Color::DarkGray,
                        Some(x) if x >= 0. => Color::Rgb(15, 83, 56),
                        _ => Color::Rgb(113, 31, 45),
                    };
                    let x = area.x + (n(&cell["x"]) as u16).min(area.width);
                    let y = area.y + 1 + (n(&cell["y"]) as u16).min(area.height - 2);
                    let width = (n(&cell["width"]) as u16).min(area.right().saturating_sub(x));
                    let height =
                        (n(&cell["height"]) as u16).min(area.bottom().saturating_sub(y + 1));
                    if width > 0 && height > 0 {
                        f.render_widget(
                            Paragraph::new(format!(
                                "{}\n{} {}\nV {}",
                                val(&item["name"]),
                                field,
                                val(&item[field]),
                                val(&item["volume"])
                            ))
                            .block(Block::default().borders(Borders::ALL))
                            .style(Style::default().bg(bg).fg(Color::White)),
                            Rect::new(x, y, width, height),
                        );
                    }
                }
            }
            f.render_widget(Paragraph::new(format!("size: completed 5m item volume · colour: {field} · s toggles margin / 1d change · top 32 by volume")),Rect::new(area.x,area.bottom()-1,area.width,1));
            return;
        }
        if w.view == "COMP" {
            let series = v["series"].as_array().cloned().unwrap_or_default();
            let points: Vec<(String, Vec<(f64, f64)>)> = series
                .iter()
                .map(|s| {
                    (
                        val(&s["name"]),
                        s["points"]
                            .as_array()
                            .into_iter()
                            .flatten()
                            .map(|p| (n(&p[0]), n(&p[1])))
                            .collect(),
                    )
                })
                .collect();
            let all: Vec<_> = points.iter().flat_map(|(_, ps)| ps.iter()).collect();
            if all.is_empty() {
                f.render_widget(Paragraph::new("No exact common observations. Use compare ID,ID; Resolution: 1w for deep history."),Rect::new(area.x,area.y+2,area.width,2));
                return;
            }
            let xmin = n(&v["time_bounds"][0]);
            let xmax = n(&v["time_bounds"][1]);
            let lo = n(&v["bounds"][0]);
            let hi = n(&v["bounds"][1]);
            let palette = [
                ACCENT,
                Color::Yellow,
                Color::Magenta,
                Color::LightBlue,
                Color::Red,
            ];
            let datasets = points
                .iter()
                .enumerate()
                .map(|(i, (name, ps))| {
                    Dataset::default()
                        .name(format!(
                            "{name} {:.1}",
                            ps.last().map(|p| p.1).unwrap_or(100.)
                        ))
                        .marker(symbols::Marker::Braille)
                        .graph_type(GraphType::Line)
                        .style(Style::default().fg(palette[i % 5]))
                        .data(ps)
                })
                .collect();
            f.render_widget(
                Chart::new(datasets)
                    .x_axis(
                        Axis::default()
                            .bounds([xmin, xmax])
                            .labels([val(&v["time_labels"][0]), val(&v["time_labels"][1])]),
                    )
                    .y_axis(Axis::default().bounds([lo, hi]).labels([
                        val(&v["ticks"][0]),
                        val(&v["ticks"][1]),
                        val(&v["ticks"][2]),
                    ]))
                    .style(Style::default().bg(BG)),
                Rect::new(area.x, area.y + 2, area.width, area.height - 4),
            );
            f.render_widget(
                Paragraph::new(format!(
                    "{} · {} · compare IDs / Range: / Resolution:",
                    val(&v["tf"]),
                    val(&v["source"])
                ))
                .style(Style::default().fg(Color::Gray)),
                Rect::new(area.x, area.bottom() - 1, area.width, 1),
            );
            return;
        }
        let (headers, fields): (Vec<&str>, Vec<&str>) = match w.view.as_str() {
            "TAS" => (
                vec!["UTC bucket", "ID", "Item", "Side", "Mean price", "Quantity"],
                vec!["timestamp", "item_id", "name", "side", "price", "volume"],
            ),
            "QM" => (
                vec![
                    "ID",
                    "Item",
                    "Bid proxy",
                    "Ask proxy",
                    "Net spread",
                    "Bid age",
                    "Ask age",
                ],
                vec![
                    "item_id", "name", "bid", "ask", "spread", "bid_time", "ask_time",
                ],
            ),
            "HCP" => (
                vec!["ID", "Item", "1d %", "1w %", "1m %", "5m volume"],
                vec![
                    "item_id",
                    "name",
                    "change_1d",
                    "change_1w",
                    "change_1m",
                    "volume",
                ],
            ),
            "MOST" => (
                vec!["ID", "Item", "5m quantity", "Trade count"],
                vec!["item_id", "name", "volume", "trade_count"],
            ),
            "AL" => (
                vec![
                    "ID",
                    "Item",
                    "Field",
                    "Direction",
                    "Threshold",
                    "State",
                    "Value",
                ],
                vec![
                    "id",
                    "item",
                    "field",
                    "direction",
                    "threshold",
                    "triggered",
                    "value",
                ],
            ),
            _ => (
                vec![
                    "ID",
                    "Item",
                    "Net spread",
                    "5m volume",
                    "Alch gap",
                    "Members",
                    "Buy limit",
                ],
                vec![
                    "item_id",
                    "name",
                    "spread",
                    "volume",
                    "alch_gap",
                    "members",
                    "buy_limit",
                ],
            ),
        };
        let rows = v["data"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|r| w.view != "AL" || w.filter.is_empty() || r.to_string().contains(&w.filter))
            .skip(w.scroll)
            .map(|r| {
                Row::new(
                    fields
                        .iter()
                        .map(|field| {
                            if *field == "timestamp" {
                                stamp(&r[*field])
                            } else if *field == "triggered" {
                                if r[*field].is_null() {
                                    "armed".into()
                                } else {
                                    format!(
                                        "FIRED {}",
                                        stamp(&serde_json::json!(n(&r[*field]) as i64))
                                    )
                                }
                            } else if ["bid_time", "ask_time"].contains(field) {
                                r[*field]
                                    .as_i64()
                                    .map(|t| format!("{}s", chrono::Utc::now().timestamp() - t))
                                    .unwrap_or_else(|| "—".into())
                            } else if *field == "trade_count" {
                                "unavailable".into()
                            } else if field.starts_with("change_") {
                                r[*field]
                                    .as_f64()
                                    .map(|x| format!("{x:+.2}%"))
                                    .unwrap_or_else(|| "—".into())
                            } else {
                                val(&r[*field])
                            }
                        })
                        .collect::<Vec<_>>(),
                )
            });
        let constraints: Vec<_> = fields
            .iter()
            .map(|field| {
                if *field == "name" {
                    Constraint::Min(22)
                } else {
                    Constraint::Length(if *field == "timestamp" { 17 } else { 14 })
                }
            })
            .collect();
        f.render_widget(
            Table::new(rows, constraints)
                .header(Row::new(headers).style(Style::default().fg(ACCENT))),
            Rect::new(area.x, area.y + 2, area.width, area.height - 4),
        );
        let footer = match w.view.as_str() {
            "EQS" => {
                "screen spread=N volume=N alch=N members=free|members limit=MIN:MAX · s rank · alch: buy+rune, fire staff, no time cost"
            }
            "QM" => "watch 855,561,4151 · age is separate for each side · no order-book depth",
            "HCP" => "s: rank 1d / 1w / 1m · absent lookbacks shown as —",
            "AL" => {
                "alert price|spread|alch_gap above|below N · alert delete ID · one-shot, persisted on server"
            }
            "MOST" => {
                "Rank: 5m item quantity · trade-count rank unavailable (not supplied by source)"
            }
            _ => "f: name filter · j/k/wheel: scroll · aggregates, not individual trades",
        };
        f.render_widget(
            Paragraph::new(footer).style(Style::default().fg(Color::Gray)),
            Rect::new(area.x, area.bottom() - 1, area.width, 1),
        );
    }
}

fn chart_height(area_h: u16, panes: u16) -> u16 {
    let pane_h = if panes == 0 {
        0
    } else {
        (area_h.saturating_sub(12) / (panes + 2)).clamp(2, 5)
    };
    area_h.saturating_sub(10 + pane_h * panes).max(2)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn app() -> (App, mpsc::UnboundedReceiver<net::Command>) {
        let (tx, mut rx) = mpsc::unbounded_channel();
        let mut app = App::new("http://test".into(), Some("Candlestick chart".into()), tx);
        while rx.try_recv().is_ok() {}
        app.width = 140;
        app.height = 40;
        app.windows[0].item = 855;
        (app, rx)
    }
    #[test]
    fn linked_tickers_propagate_without_changing_unlinked_windows_or_studies() {
        let (mut app, mut rx) = app();
        app.windows[0].link = "red".into();
        app.windows[0].set("style", "Renko");
        let mut monitor = app.windows[0].clone();
        monitor.view = "QM".into();
        monitor.id = 2;
        monitor.options = serde_json::json!({"ids":[855,561]});
        let mut isolated = monitor.clone();
        isolated.id = 3;
        isolated.link = "blue".into();
        app.windows.insert(0, isolated);
        app.windows.insert(0, monitor);
        app.set_ticker(4151);
        assert_eq!(
            app.windows.iter().map(|w| w.item).collect::<Vec<_>>(),
            vec![4151, 855, 4151]
        );
        assert_eq!(app.windows.last().unwrap().option("style", ""), "Renko");
        app.sync_terminal();
        let requests: Vec<_> = std::iter::from_fn(|| rx.try_recv().ok())
            .filter_map(|c| {
                if let net::Command::Terminal(_, _, body) = c {
                    Some(body)
                } else {
                    None
                }
            })
            .collect();
        assert_eq!(requests.len(), 3);
        assert!(requests[0].get("offset").is_none());
        assert_eq!(requests[0]["linked"], true);
    }
    #[test]
    fn close_undo_restores_exact_window_and_link_configuration() {
        let (mut app, _) = app();
        app.windows[0].link = "green".into();
        app.windows[0].set("style", "Point & Figure");
        let before = serde_json::to_value(&app.windows).unwrap();
        app.close_focused();
        assert!(app.windows.is_empty());
        app.undo_close();
        assert_eq!(serde_json::to_value(&app.windows).unwrap(), before);
        app.undo_close();
        assert_eq!(app.windows.len(), 1);
    }
    #[test]
    fn chart_panes_and_help_render_on_tiny_and_full_terminals() {
        let (mut app, _) = app();
        app.data.insert("terminal:1".into(),serde_json::json!({"item":855,"tf":"1d","style":"Heikin Ashi","scale":"percent","provenance":"mean-envelope; NOT trade OHLC","bounds":[-1.,1.],"count":2,"lines":[],"rects":[],"panes":[],"labels":[],"ticks":[]}));
        for (width, height) in [(1, 1), (20, 8), (80, 24), (140, 46)] {
            let backend = ratatui::backend::TestBackend::new(width, height);
            let mut terminal = Terminal::new(backend).unwrap();
            app.clamp(width, height);
            terminal.draw(|f| app.draw(f)).unwrap();
            app.help = true;
            terminal.draw(|f| app.draw(f)).unwrap();
            app.help = false;
        }
        assert!(chart_height(44, 2) >= 20);
    }
}
