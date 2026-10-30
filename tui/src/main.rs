mod charts;
mod chat;
mod drag;
mod interaction;
mod net;
mod profile;
mod search;
mod search_ui;
mod terminal;
mod views;
mod window;

use crossterm::{
    event::{
        self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode, KeyModifiers, MouseButton,
        MouseEventKind,
    },
    execute,
    terminal::{EnterAlternateScreen, LeaveAlternateScreen, disable_raw_mode, enable_raw_mode},
};
use ratatui::{
    prelude::*,
    widgets::{Block, Borders, Clear, Paragraph, Row, Table, Wrap},
};
use serde_json::Value;
use std::{
    collections::HashMap,
    fs, io,
    path::PathBuf,
    time::{Duration, Instant},
};
use tokio::sync::mpsc;
use window::{Bounds, Hit, Window};

const VIEWS: &[&str] = &[
    "G chart",
    "GP chart",
    "GIP intraday",
    "GPO bars",
    "GPL line",
    "GPC candles",
    "GPF area",
    "TAS",
    "QM",
    "HCP",
    "HMAP",
    "MOST",
    "EQS",
    "COMP",
    "AL",
    "HELP",
    "Style: Candles",
    "Style: Bars",
    "Style: Line",
    "Style: Area",
    "Style: Baseline",
    "Style: Heikin Ashi",
    "Style: Hollow Candles",
    "Style: Renko",
    "Style: Kagi",
    "Style: Point & Figure",
    "Style: Line Break",
    "Scale: linear",
    "Scale: percent",
    "Scale: indexed",
    "Scale: logarithmic",
    "Scale: invert",
    "Scale: axis left",
    "Scale: auto fit",
    "Scale: lock ratio",
    "Scale: price only",
    "Range: 5y",
    "Range: 1y",
    "Range: 6m",
    "Range: 3m",
    "Range: 1m",
    "Range: 5d",
    "Range: 1d",
    "Resolution: 5m",
    "Resolution: 15m",
    "Resolution: 30m",
    "Resolution: 1h",
    "Resolution: 1d",
    "Resolution: 1w",
    "Indicator: SMA",
    "Indicator: EMA",
    "Indicator: BOLL",
    "Indicator: RSI",
    "Indicator: MACD",
    "Indicator: VWAP",
    "Link: none",
    "Link: red",
    "Link: green",
    "Link: blue",
    "Link: yellow",
    "Link: magenta",
    "Undo close",
    "Hermes chat",
    "chat with Codex",
    "chat with Hermes",
    "Chat: enable writes",
    "Chat: read-only",
    "Chat log",
    "Chat: new conversation",
    "Chat: next conversation",
    "Market table",
    "Alchemy gaps",
    "Candlestick chart",
    "Metric series",
    "Movers screener",
    "Jobs",
    "Model results",
    "Collector health",
    "Log console",
    "Research battery",
    "Participation",
    "Start benchmark",
    "Start eval",
    "Start train",
    "Start backtest",
    "Dataset: synthetic",
    "Dataset: development",
    "Track: price_only",
    "Track: full_feature",
    "Track: frozen_daily",
    "Preset: all",
    "Preset: conservative",
    "Preset: moderate",
    "Preset: optimistic",
    "Horizon: 1",
    "Horizon: 4",
    "Horizon: 24",
];
const BG: Color = Color::Rgb(11, 18, 28);
const FG: Color = Color::Rgb(202, 216, 224);
const ACCENT: Color = Color::Rgb(89, 210, 185);

struct Screen;
impl Drop for Screen {
    fn drop(&mut self) {
        let _ = disable_raw_mode();
        let _ = execute!(io::stdout(), DisableMouseCapture, LeaveAlternateScreen);
    }
}
struct Drag {
    rect: Bounds,
    x: u16,
    y: u16,
    resize: Option<window::Handle>,
    pan: bool,
    offset: usize,
}
struct RowPress {
    press: interaction::Press,
    window: u64,
    row: usize,
    item: u64,
    shift: bool,
}
struct PendingClick {
    selection: RowPress,
    at: Instant,
}
struct App {
    windows: Vec<Window>,
    closed: Vec<Vec<Window>>,
    search: search_ui::SearchUi,
    next_id: u64,
    help: bool,
    help_scroll: u16,
    last_escape: Option<Instant>,
    notice: String,
    data: HashMap<String, Value>,
    received: HashMap<String, Instant>,
    connected: bool,
    errors: Vec<String>,
    palette: Option<String>,
    palette_index: usize,
    filtering: bool,
    drag: Option<Drag>,
    row_press: Option<RowPress>,
    pending_click: Option<PendingClick>,
    drag_scene: Option<drag::Scene>,
    width: u16,
    height: u16,
    server: String,
    commands: mpsc::UnboundedSender<net::Command>,
    item: u64,
    hover: Option<(u16, u16)>,
    selected_job: String,
    job_events: HashMap<String, Vec<Value>>,
    stream_state: String,
    metric: String,
    dataset: String,
    track: String,
    preset: String,
    horizon: u64,
    chat: chat::ChatUi,
}
fn layout_path() -> PathBuf {
    PathBuf::from(std::env::var("XDG_CONFIG_HOME").unwrap_or_else(|_| {
        format!(
            "{}/.config",
            std::env::var("HOME").unwrap_or_else(|_| ".".into())
        )
    }))
    .join("osrs-term/layout.json")
}
impl App {
    fn new(
        server: String,
        view: Option<String>,
        commands: mpsc::UnboundedSender<net::Command>,
    ) -> Self {
        let mut windows = if let Some(view) = view {
            vec![Window {
                view,
                rect: Bounds {
                    x: 0,
                    y: 0,
                    w: 160,
                    h: 40,
                },
                scroll: 0,
                filter: String::new(),
                sort: 0,
                ..Window::default()
            }]
        } else {
            window::decode_layout(fs::read(layout_path()).ok().as_deref())
        };
        let state: Value = fs::read(layout_path().with_file_name("state.json"))
            .ok()
            .and_then(|v| serde_json::from_slice(&v).ok())
            .unwrap_or(Value::Null);
        for (i, w) in windows.iter_mut().enumerate() {
            w.id = i as u64 + 1;
            if w.item == 0 {
                w.item = state["item"].as_u64().unwrap_or(855);
            }
        }
        let next_id = windows.len() as u64 + 1;
        let app = Self {
            windows,
            closed: vec![],
            search: search_ui::SearchUi::load(),
            next_id,
            help: false,
            help_scroll: 0,
            last_escape: None,
            notice: String::new(),
            data: HashMap::new(),
            received: HashMap::new(),
            connected: false,
            errors: vec![],
            palette: None,
            palette_index: 0,
            filtering: false,
            drag: None,
            row_press: None,
            pending_click: None,
            drag_scene: None,
            width: 0,
            height: 0,
            server: server.clone(),
            commands,
            item: state["item"].as_u64().unwrap_or(855),
            hover: None,
            selected_job: state["selected_job"].as_str().unwrap_or("").into(),
            job_events: HashMap::new(),
            stream_state: "detached".into(),
            metric: state["metric"].as_str().unwrap_or("net_gp_per_hour").into(),
            dataset: state["dataset"].as_str().unwrap_or("synthetic").into(),
            track: state["track"].as_str().unwrap_or("price_only").into(),
            preset: state["preset"].as_str().unwrap_or("conservative").into(),
            horizon: state["horizon"].as_u64().unwrap_or(1),
            chat: chat::ChatUi::new(&state, &server),
        };
        if !app.chat.id.is_empty() {
            let _ = app
                .commands
                .send(net::Command::ChatWatch(app.chat.id.clone()));
        }
        if !app.selected_job.is_empty() {
            let _ = app
                .commands
                .send(net::Command::Watch(app.selected_job.clone()));
        }
        app
    }
    #[cfg(test)]
    fn save(&mut self) {}
    #[cfg(not(test))]
    fn save(&mut self) {
        let path = layout_path();
        let result = (|| -> io::Result<()> {
            fs::create_dir_all(path.parent().unwrap())?;
            fs::write(
                path.with_extension("tmp"),
                serde_json::to_vec_pretty(&self.windows)?,
            )?;
            fs::rename(path.with_extension("tmp"), &path)?;
            let state = serde_json::json!({"item":self.item,"selected_job":self.selected_job,"metric":self.metric,"dataset":self.dataset,"track":self.track,"preset":self.preset,"horizon":self.horizon,"chat_id":self.chat.id,"chat_server":self.server,"chat_target":self.chat.target,"chat_workdir":self.chat.workdir});
            fs::write(
                path.with_file_name("state.tmp"),
                serde_json::to_vec(&state)?,
            )?;
            fs::rename(
                path.with_file_name("state.tmp"),
                path.with_file_name("state.json"),
            )
        })();
        if let Err(e) = result {
            self.errors.push(format!("Layout: {e}"));
        }
    }
    fn clamp(&mut self, width: u16, height: u16) {
        self.width = width;
        self.height = height.saturating_sub(2);
        for w in &mut self.windows {
            w.rect = window::clamp(w.rect, self.width, self.height);
        }
    }
    fn add(&mut self, view: String) {
        let n = self.windows.len() as u16;
        self.windows.push(Window {
            view,
            rect: window::clamp(
                Bounds {
                    x: 4u16.saturating_add(n.saturating_mul(2)),
                    y: 2u16.saturating_add(n),
                    w: 130,
                    h: 32,
                },
                self.width,
                self.height,
            ),
            scroll: 0,
            filter: String::new(),
            sort: 0,
            id: self.next_id,
            item: self.windows.last().map(|w| w.item).unwrap_or(self.item),
            link: self
                .windows
                .last()
                .map(|w| w.link.clone())
                .unwrap_or_default(),
            ..Window::default()
        });
        self.next_id += 1;
        self.save();
    }
    fn choose_job(&mut self, id: String) {
        if id != self.selected_job {
            self.selected_job = id.clone();
            self.stream_state = "attaching / replaying".into();
            let _ = self.commands.send(net::Command::Watch(id));
            self.save();
        }
    }
    fn action(&mut self, action: String) {
        if self.terminal_action(&action) {
            self.save();
            return;
        }
        if action == "chat with Codex" || action == "chat with Hermes" {
            self.switch_target(if action.ends_with("Codex") {
                "codex"
            } else {
                "hermes"
            });
        } else if let Some(dir) = action.strip_prefix("Chat workdir: ") {
            if self.chat.pending
                || self
                    .data
                    .get("chat")
                    .is_some_and(|v| v["status"] == "running")
            {
                self.chat
                    .errors
                    .push("Cancel or finish the turn before changing workdir".into());
                return;
            }
            self.new_chat();
            self.chat.workdir = dir.into();
            self.switch_target("codex");
        } else if action == "Chat: enable writes" || action == "Chat: read-only" {
            if self.chat.target == "codex"
                && !self.chat.pending
                && !self
                    .data
                    .get("chat")
                    .is_some_and(|v| v["status"] == "running")
            {
                // A mode choice creates a new conversation so pending configuration
                // cannot be overwritten by an older transcript arriving over the wire.
                self.new_chat();
                self.chat.allow_writes = action == "Chat: enable writes";
                self.chat.confirmation = format!(
                    "Codex mode: {}",
                    if self.chat.allow_writes {
                        "workspace-write"
                    } else {
                        "read-only"
                    }
                );
            }
        } else if action == "Chat: new conversation" {
            self.new_chat();
        } else if action == "Chat: next conversation" {
            self.next_chat();
        } else if let Some(kind) = action.strip_prefix("Start ") {
            let params = serde_json::json!({"dataset":self.dataset,"track":self.track,"preset":self.preset,"horizon_hours":self.horizon});
            self.errors.push(format!("Starting {kind}: {params}"));
            let _ = self.commands.send(net::Command::Start(kind.into(), params));
            if !self.windows.last().is_some_and(|w| w.view == "Jobs") {
                self.add("Jobs".into());
            }
        } else if let Some(value) = action.strip_prefix("Dataset: ") {
            self.dataset = value.into();
            if value == "development" {
                self.horizon = 24;
                self.track = "frozen_daily".into();
                self.preset = "all".into();
            } else {
                self.horizon = 1;
                self.track = "price_only".into();
                self.preset = "conservative".into();
            }
        } else if let Some(value) = action.strip_prefix("Track: ") {
            self.track = value.into();
        } else if let Some(value) = action.strip_prefix("Preset: ") {
            self.preset = value.into();
        } else if let Some(value) = action.strip_prefix("Horizon: ") {
            self.horizon = value.parse().unwrap_or(1);
        } else {
            self.add(action);
        }
        self.save();
    }
    fn market_rows(&self, w: &Window) -> Vec<&Value> {
        self.item_rows(w)
    }
    fn item_rows(&self, w: &Window) -> Vec<&Value> {
        let key = match w.view.as_str() {
            "Market table" => "prices/latest".into(),
            "Movers screener" => "prices/movers".into(),
            _ => format!("terminal:{}", w.id),
        };
        self.data
            .get(&key)
            .map(|data| interaction::rows(&w.view, data, &w.filter, w.sort))
            .unwrap_or_default()
    }
    fn row_item(&self, w: &Window, x: u16, y: u16) -> Option<(usize, u64)> {
        if w.view == "HMAP" {
            let v = self.data.get(&format!("terminal:{}", w.id))?;
            for (i, cell) in v["cells"].as_array()?.iter().enumerate() {
                let rect = interaction::tile_bounds(
                    Bounds {
                        x: w.rect.x + 1,
                        y: w.rect.y + 1,
                        w: w.rect.w.saturating_sub(2),
                        h: w.rect.h.saturating_sub(2),
                    },
                    cell,
                )?;
                if rect.contains(x, y)
                    && x > rect.x
                    && y > rect.y
                    && x + 1 < rect.x + rect.w
                    && y + 1 < rect.y + rect.h
                {
                    return Some((i, cell["item"]["item_id"].as_u64()?));
                }
            }
            return None;
        }
        if ![
            "Market table",
            "Movers screener",
            "TAS",
            "QM",
            "HCP",
            "MOST",
            "EQS",
            "COMP",
            "AL",
        ]
        .contains(&w.view.as_str())
        {
            return None;
        }
        if terminal::panel_view(&w.view) && (w.rect.w < 12 || w.rect.h < 6) {
            return None;
        }
        let rows = self.item_rows(w);
        let headers = if ["Market table", "Movers screener"].contains(&w.view.as_str()) {
            2
        } else {
            3
        };
        let footer = match w.view.as_str() {
            "Market table" => 1,
            "Movers screener" => 0,
            _ => 2,
        };
        let count = if w.view == "COMP" {
            rows.len().min(5)
        } else {
            rows.len()
        };
        let index = interaction::row_at(w.rect, x, y, headers, footer, w.scroll, count)?;
        Some((index, interaction::item_id(rows.get(index)?)?))
    }
    fn chart_click(&mut self, selection: RowPress, new: bool) {
        let Some(source) = self
            .windows
            .iter()
            .find(|w| w.id == selection.window)
            .cloned()
        else {
            return;
        };
        if selection.shift {
            let pos = self
                .windows
                .iter()
                .position(|w| w.view == "COMP" && w.link == source.link);
            if let Some(pos) = pos {
                let w = &mut self.windows[pos];
                let mut ids: Vec<u64> = w.options["ids"]
                    .as_array()
                    .map(|a| a.iter().filter_map(Value::as_u64).collect())
                    .unwrap_or_else(|| vec![855, 561, 4151]);
                if !w.link.is_empty() && !ids.is_empty() {
                    ids[0] = w.item;
                }
                if !ids.contains(&selection.item) && ids.len() < 5 {
                    ids.push(selection.item);
                }
                w.set("ids", serde_json::json!(ids));
            } else {
                self.add("COMP".into());
                let w = self.windows.last_mut().unwrap();
                w.link = source.link;
                w.set("ids", serde_json::json!([selection.item]));
            }
            self.save();
            return;
        }
        if !new {
            for w in &mut self.windows {
                if w.id == source.id || !source.link.is_empty() && w.link == source.link {
                    w.item = selection.item;
                    if w.view == "Candlestick chart" {
                        w.set("offset", 0);
                    }
                }
            }
        }
        let existing = if new {
            None
        } else {
            self.windows
                .iter()
                .position(|w| w.view == "Candlestick chart" && w.link == source.link)
        };
        if let Some(pos) = existing {
            let mut chart = self.windows.remove(pos);
            chart.item = selection.item;
            chart.set("offset", 0);
            self.windows.push(chart);
        } else {
            self.add("Candlestick chart".into());
            let w = self.windows.last_mut().unwrap();
            w.item = selection.item;
            // An independent double-click chart must not join the source link group.
            w.link = if new { String::new() } else { source.link };
        }
        self.item = selection.item;
        self.save();
    }
    fn flush_click(&mut self) -> bool {
        if self.drag.is_some() || self.row_press.is_some() {
            return false;
        }
        if self
            .pending_click
            .as_ref()
            .is_some_and(|c| c.at.elapsed() >= Duration::from_millis(300))
        {
            let c = self.pending_click.take().unwrap();
            self.chart_click(c.selection, false);
            return true;
        }
        false
    }
    fn rows(&self, key: &str) -> Vec<&Value> {
        self.data
            .get(key)
            .and_then(|v| v["data"].as_array())
            .map(|v| v.iter().collect())
            .unwrap_or_default()
    }
    fn freshness(&self, key: &str) -> String {
        match self.data.get(key) {
            None => "ABSENT • waiting for server".into(),
            Some(v) => format!(
                "{} • fetched {}s ago{}",
                if !self.connected || v["stale"] == true {
                    "STALE"
                } else {
                    "LIVE"
                },
                v["age_seconds"].as_f64().unwrap_or(0.) as u64
                    + self
                        .received
                        .get(key)
                        .map(|t| t.elapsed().as_secs())
                        .unwrap_or(0),
                v["error"]
                    .as_str()
                    .map(|e| format!(" • {e}"))
                    .unwrap_or_default()
            ),
        }
    }
    fn draw(&self, f: &mut Frame) {
        if let (Some(scene), Some(w)) = (&self.drag_scene, self.windows.last()) {
            scene.draw(f, Rect::new(w.rect.x, w.rect.y, w.rect.w, w.rect.h));
            return;
        }
        self.draw_full(f, false);
    }
    fn draw_full(&self, f: &mut Frame, skip_focused: bool) {
        let area = f.area();
        f.render_widget(Block::default().style(Style::default().bg(BG).fg(FG)), area);
        if self.windows.is_empty() {
            f.render_widget(
                Paragraph::new("  Press / or Ctrl+K to add a window · 1 recent  2 pin  3 top movers  4 alch gaps")
                    .style(Style::default().fg(ACCENT)),
                area,
            );
        }
        for (i, w) in self.windows.iter().enumerate() {
            if skip_focused && i + 1 == self.windows.len() {
                continue;
            }
            let r = Rect::new(w.rect.x, w.rect.y, w.rect.w, w.rect.h);
            let focus = i + 1 == self.windows.len();
            f.render_widget(Clear, r);
            let block = Block::default()
                .borders(Borders::ALL)
                .title(format!(
                    " {} {} {}{} ",
                    if focus { "◆" } else { "◇" },
                    if w.view == "Candlestick chart" {
                        "G / GP chart"
                    } else if w.view == "Hermes chat" {
                        "Agent chat"
                    } else {
                        &w.view
                    },
                    if w.link.is_empty() {
                        String::new()
                    } else {
                        format!("[{}:{}]", w.link, w.item)
                    },
                    if focus && self.drag.as_ref().is_some_and(|d| d.resize.is_some()) {
                        format!(" {}x{}", w.rect.w, w.rect.h)
                    } else {
                        String::new()
                    }
                ))
                .border_style(Style::default().fg(if !w.link.is_empty() {
                    terminal::link_color(&w.link)
                } else if focus {
                    ACCENT
                } else {
                    Color::DarkGray
                }))
                .style(Style::default().bg(BG).fg(FG));
            let inner = block.inner(r);
            f.render_widget(block, r);
            if r.width >= 4 {
                f.render_widget(
                    Paragraph::new("×").style(Style::default().fg(Color::Red)),
                    Rect::new(r.right() - 3, r.y, 1, 1),
                );
            }
            match w.view.as_str() {
                "Doc viewer" => f.render_widget(
                    Paragraph::new(w.option("body", "").to_string())
                        .wrap(Wrap { trim: false })
                        .scroll((w.scroll as u16, 0)),
                    inner,
                ),
                "Market table" => self.market(f, inner, w),
                "Alchemy gaps" => self.alchemy(f, inner, w),
                "Candlestick chart" => self.terminal_chart(f, inner, w),
                "TAS" | "QM" | "HCP" | "HMAP" | "MOST" | "EQS" | "COMP" | "AL" => {
                    self.terminal_panel(f, inner, w)
                }
                "Metric series" => charts::line(f, inner, &self.metric_points(), &self.metric),
                "Jobs" => self.jobs(f, inner, w),
                "Hermes chat" => self.chat_view(f, inner, w),
                "Chat log" => {
                    let text = self
                        .data
                        .get("chat_progress")
                        .and_then(|v| v["text"].as_str())
                        .unwrap_or("No progress yet. Start a turn in the chat panel.");
                    f.render_widget(
                        Paragraph::new(format!(
                            "{} · {}\n{}",
                            self.chat.target, self.chat.id, text
                        ))
                        .wrap(Wrap { trim: false })
                        .scroll((w.scroll.min(u16::MAX as usize) as u16, 0)),
                        inner,
                    );
                }
                "Movers screener" => self.movers(f, inner, w),
                "Model results" => self.models(f, inner, w),
                "Collector health" => self.collector(f, inner, w),
                "Log console" => self.console(f, inner, w),
                "Research battery" => self.research_table(f, inner, w, true),
                "Participation" => self.research_table(f, inner, w, false),
                _ => f.render_widget(Paragraph::new("Unknown view"), inner),
            }
        }
        let clock = chrono::Local::now().format("%H:%M:%S");
        let status = format!(
            " OSRS TERM  {clock}  {}  {}  windows:{}   {}",
            if self.connected {
                "CONNECTED"
            } else {
                "OFFLINE / reconnecting"
            },
            self.server,
            self.windows.len(),
            format!("{} {}", self.alert_flash(), self.notice)
        );
        f.render_widget(
            Paragraph::new(status).style(
                Style::default()
                    .bg(
                        if !self.alert_flash().is_empty() && chrono::Utc::now().timestamp() % 2 == 0
                        {
                            Color::Rgb(120, 25, 25)
                        } else {
                            Color::Rgb(23, 40, 51)
                        },
                    )
                    .fg(ACCENT),
            ),
            Rect::new(0, area.height.saturating_sub(2), area.width, 1),
        );
        let help = if self.windows.is_empty() {
            ""
        } else if self.windows.last().is_some_and(|w| w.view == "Hermes chat") && self.chat.editing
        {
            " Enter send  Alt+Enter/Ctrl+J newline  Ctrl+X cancel  Esc leave input  Ctrl+P palette  Tab focus  Ctrl+W close"
        } else if self.filtering {
            " Filter: type text · Enter finish · Esc clear"
        } else {
            " ` / Ctrl+P palette  F1 help  Tab focus  C styles  S scales  I studies  R range  Ctrl+Z undo  q quit"
        };
        f.render_widget(
            Paragraph::new(help).style(Style::default().fg(Color::Gray)),
            Rect::new(0, area.height.saturating_sub(1), area.width, 1),
        );
        if self.help {
            self.draw_help(f, area);
        }
        if self.palette.is_some() {
            self.draw_search(f, area);
        }
    }

    fn market(&self, f: &mut Frame, area: Rect, w: &Window) {
        if area.height < 2 {
            return;
        }
        f.render_widget(
            Paragraph::new(format!(
                "{}  filter:{}  sort:{}",
                self.freshness("prices/latest"),
                w.filter,
                ["item", "margin ↓", "buy ↓"][w.sort as usize % 3]
            )),
            Rect::new(area.x, area.y, area.width, 1),
        );
        let rows = self.market_rows(w);
        let rows = rows.into_iter().skip(w.scroll).map(|r| {
            Row::new([
                val(&r["item_id"]),
                val(&r["name"]),
                val(&r["buy_price"]),
                val(&r["sell_price"]),
                val(&r["margin_gp"]),
            ])
            .style(
                Style::default()
                    .bg(if w.options["selected_item"] == r["item_id"] {
                        Color::DarkGray
                    } else {
                        BG
                    })
                    .fg(if r["margin_gp"].as_i64().unwrap_or(0) > 0 {
                        Color::Green
                    } else {
                        Color::Red
                    }),
            )
        });
        let table = Table::new(
            rows,
            [
                Constraint::Length(8),
                Constraint::Min(24),
                Constraint::Length(16),
                Constraint::Length(16),
                Constraint::Length(16),
            ],
        )
        .header(
            Row::new(["ID", "Item", "Instant buy", "Instant sell", "Net spread*"])
                .style(Style::default().fg(ACCENT)),
        )
        .row_highlight_style(Style::default().bg(Color::DarkGray));
        f.render_widget(
            table,
            Rect::new(
                area.x,
                area.y + 1,
                area.width,
                area.height.saturating_sub(2),
            ),
        );
        if area.height > 4 {
            f.render_widget(
                Paragraph::new(
                    "*Hypothetical low purchase / high sale after tax; server calculation",
                )
                .style(Style::default().fg(Color::Gray)),
                Rect::new(area.x, area.bottom() - 1, area.width, 1),
            );
        }
    }
    fn alchemy(&self, f: &mut Frame, area: Rect, w: &Window) {
        if area.height < 3 {
            return;
        }
        f.render_widget(
            Paragraph::new(self.freshness("alch/gaps")),
            Rect::new(area.x, area.y, area.width, 1),
        );
        let rows = self
            .rows("alch/gaps")
            .into_iter()
            .filter(|r| {
                r["name"]
                    .as_str()
                    .unwrap_or("")
                    .to_lowercase()
                    .contains(&w.filter.to_lowercase())
            })
            .skip(w.scroll)
            .map(|r| {
                Row::new([
                    val(&r["name"]),
                    val(&r["buy_price"]),
                    val(&r["high_alch"]),
                    val(&r["nature_rune_cost"]),
                    val(&r["net_gap_gp"]),
                    val(&r["capacity"]),
                ])
                .style(Style::default().fg(
                    if r["net_gap_gp"].as_f64().unwrap_or(0.) > 0. {
                        Color::Green
                    } else {
                        Color::Red
                    },
                ))
            });
        f.render_widget(
            Table::new(
                rows,
                [
                    Constraint::Min(23),
                    Constraint::Length(12),
                    Constraint::Length(12),
                    Constraint::Length(12),
                    Constraint::Length(12),
                    Constraint::Length(12),
                ],
            )
            .header(
                Row::new([
                    "Item",
                    "Buy mean",
                    "High alch",
                    "Nature rune",
                    "Net gap",
                    "Capacity*",
                ])
                .style(Style::default().fg(ACCENT)),
            ),
            Rect::new(
                area.x,
                area.y + 2,
                area.width,
                area.height.saturating_sub(4),
            ),
        );
        f.render_widget(
            Paragraph::new(
                "*Conditional capacity, 5m means + research assumptions; not observed fills",
            )
            .wrap(Wrap { trim: true })
            .style(Style::default().fg(Color::Gray)),
            Rect::new(area.x, area.bottom().saturating_sub(2), area.width, 2),
        );
    }
    fn key(&mut self, code: KeyCode, modifiers: KeyModifiers) -> bool {
        if code == KeyCode::F(1) {
            self.help = !self.help;
            self.palette = None;
            if self.help {
                self.help_scroll = 0;
            }
            return false;
        }
        if self.help {
            match code {
                KeyCode::Esc => self.help = false,
                KeyCode::Char('j') | KeyCode::Down => {
                    self.help_scroll = (self.help_scroll + 1).min(40)
                }
                KeyCode::Char('k') | KeyCode::Up => {
                    self.help_scroll = self.help_scroll.saturating_sub(1)
                }
                KeyCode::PageDown => self.help_scroll = (self.help_scroll + 10).min(40),
                KeyCode::PageUp => self.help_scroll = self.help_scroll.saturating_sub(10),
                _ => {}
            }
            return false;
        }
        if self.palette.is_some() {
            self.search_key(code, modifiers);
            return false;
        }
        if self.windows.last().is_some_and(|w| w.view == "Hermes chat")
            && !(code == KeyCode::Char('k') && modifiers.contains(KeyModifiers::CONTROL))
            && self.chat_key(code, modifiers)
        {
            return false;
        }
        if self.filtering {
            if let Some(w) = self.windows.last_mut() {
                match code {
                    KeyCode::Enter => self.filtering = false,
                    KeyCode::Esc => {
                        w.filter.clear();
                        self.filtering = false
                    }
                    KeyCode::Backspace => {
                        w.filter.pop();
                        w.scroll = 0
                    }
                    KeyCode::Char(c) => {
                        w.filter.push(c);
                        w.scroll = 0
                    }
                    _ => {}
                }
            }
            return false;
        }
        if code == KeyCode::Char('`')
            || code == KeyCode::Char('/')
            || matches!(code, KeyCode::Char('p' | 'k')) && modifiers.contains(KeyModifiers::CONTROL)
        {
            self.palette = Some(String::new());
            self.palette_index = 0;
            self.search_changed();
            return false;
        }
        if self.windows.is_empty() {
            match code {
                KeyCode::Char('1' | '2') => {
                    let key = if code == KeyCode::Char('1') {
                        self.search.prefs.recent.first()
                    } else {
                        self.search.prefs.pins.first()
                    }
                    .cloned();
                    if let Some(key) = key {
                        self.palette = Some(String::new());
                        self.search_changed();
                        if let Some(i) = self
                            .search
                            .hits
                            .iter()
                            .position(|h| self.search.entries[h.entry].key == key)
                        {
                            self.palette_index = i;
                            self.search_key(KeyCode::Enter, KeyModifiers::empty());
                        }
                    }
                    return false;
                }
                KeyCode::Char('3') => {
                    self.add("Movers screener".into());
                    return false;
                }
                KeyCode::Char('4') => {
                    self.add("Alchemy gaps".into());
                    return false;
                }
                _ => {}
            }
        }
        let focused = self.windows.last().map(|w| w.view.as_str()).unwrap_or("");
        if focused == "Candlestick chart" {
            let picker = match code {
                KeyCode::Char('C') => Some("Style: "),
                KeyCode::Char('S') => Some("Scale: "),
                KeyCode::Char('I') => Some("Indicator: "),
                KeyCode::Char('R') => Some("Range: "),
                _ => None,
            };
            if let Some(prefix) = picker {
                self.palette = Some(prefix.into());
                self.palette_index = 0;
                self.search_changed();
                return false;
            }
            if let KeyCode::Char(c @ ('1' | '2' | '3' | '4' | '5' | '6')) = code {
                if let Some(w) = self.windows.last_mut() {
                    w.set(
                        "tf",
                        match c {
                            '1' => "5m",
                            '2' => "15m",
                            '3' => "30m",
                            '4' => "1h",
                            '5' => "1d",
                            _ => "1w",
                        },
                    );
                    w.set("offset", 0);
                }
                self.save();
                return false;
            }
            if matches!(code, KeyCode::Char('j' | 'k')) {
                if let Some(w) = self.windows.last_mut() {
                    let offset = w.options["offset"].as_u64().unwrap_or(0);
                    w.set(
                        "offset",
                        if code == KeyCode::Char('j') {
                            offset.saturating_add(1)
                        } else {
                            offset.saturating_sub(1)
                        },
                    );
                }
                self.save();
                return false;
            }
            if matches!(code, KeyCode::Char('+' | '=' | '-')) {
                self.zoom_chart(code != KeyCode::Char('-'));
                return false;
            }
        }
        if ["Market table", "Movers screener"].contains(&focused) && code == KeyCode::Enter {
            if let Some(w) = self.windows.last() {
                if let Some(id) = self
                    .market_rows(w)
                    .get(w.scroll)
                    .and_then(|r| r["item_id"].as_u64())
                {
                    self.set_ticker(id);
                    self.add("Candlestick chart".into());
                }
            }
            return false;
        }
        if ["TAS", "QM", "HCP", "MOST", "EQS"].contains(&focused) && code == KeyCode::Enter {
            let selected = self
                .windows
                .last()
                .and_then(|w| {
                    self.data
                        .get(&format!("terminal:{}", w.id))
                        .and_then(|v| v["data"].as_array())
                        .and_then(|rows| rows.get(w.scroll))
                })
                .and_then(|r| r["item_id"].as_u64());
            if let Some(id) = selected {
                self.set_ticker(id);
                self.add("Candlestick chart".into());
            }
            return false;
        }
        if focused == "Jobs" {
            if code == KeyCode::Char('c') && !self.selected_job.is_empty() {
                let _ = self
                    .commands
                    .send(net::Command::Cancel(self.selected_job.clone()));
                return false;
            }
            if matches!(code, KeyCode::Char('j' | 'k')) {
                let rows = self.rows("jobs");
                let i = rows
                    .iter()
                    .position(|r| r["id"] == self.selected_job)
                    .unwrap_or(0);
                let next = if code == KeyCode::Char('j') {
                    (i + 1).min(rows.len().saturating_sub(1))
                } else {
                    i.saturating_sub(1)
                };
                let id = rows
                    .get(next)
                    .and_then(|r| r["id"].as_str())
                    .map(str::to_string);
                if let Some(id) = id {
                    self.choose_job(id);
                }
                return false;
            }
        }
        match code {
            KeyCode::Char('q') => return true,
            KeyCode::Esc => {
                if self
                    .last_escape
                    .is_some_and(|t| t.elapsed() < Duration::from_millis(500))
                {
                    self.close_focused();
                    self.last_escape = None;
                } else {
                    self.last_escape = Some(Instant::now());
                }
            }
            KeyCode::Char('z') if modifiers.contains(KeyModifiers::CONTROL) => self.undo_close(),
            KeyCode::BackTab => {
                if self.windows.len() > 1 {
                    let w = self.windows.pop().unwrap();
                    self.windows.insert(0, w);
                }
            }
            KeyCode::Tab => {
                if self.windows.len() > 1 {
                    let w = self.windows.remove(0);
                    self.windows.push(w);
                }
            }
            KeyCode::Char('w') if modifiers.contains(KeyModifiers::CONTROL) => {
                self.close_focused();
            }
            KeyCode::Char('f') => self.filtering = true,
            _ => {
                if let Some(w) = self.windows.last_mut() {
                    match code {
                        KeyCode::Char('s') => {
                            w.sort = (w.sort + 1) % if w.view == "HMAP" { 2 } else { 3 }
                        }
                        KeyCode::Char('j') => w.scroll = w.scroll.saturating_add(1),
                        KeyCode::Char('k') => w.scroll = w.scroll.saturating_sub(1),
                        KeyCode::Char('m') => {
                            w.rect = Bounds {
                                x: 0,
                                y: 0,
                                w: self.width,
                                h: self.height,
                            }
                        }
                        KeyCode::Left | KeyCode::Right | KeyCode::Up | KeyCode::Down => {
                            let (dx, dy) = match code {
                                KeyCode::Left => (-1, 0),
                                KeyCode::Right => (1, 0),
                                KeyCode::Up => (0, -1),
                                _ => (0, 1),
                            };
                            w.rect = if modifiers
                                .contains(KeyModifiers::CONTROL | KeyModifiers::SHIFT)
                            {
                                window::edge(w.rect, dx, dy, self.width, self.height, false)
                            } else if modifiers.contains(KeyModifiers::ALT | KeyModifiers::SHIFT) {
                                window::edge(w.rect, dx, dy, self.width, self.height, true)
                            } else if modifiers.contains(KeyModifiers::ALT) {
                                window::keyboard_resize(
                                    w.rect,
                                    dx,
                                    dy,
                                    modifiers.contains(KeyModifiers::CONTROL),
                                    self.width,
                                    self.height,
                                )
                            } else if modifiers.contains(KeyModifiers::SHIFT) {
                                window::translate(w.rect, dx, dy, self.width, self.height)
                            } else {
                                window::translate(w.rect, dx, dy, self.width, self.height)
                            };
                        }
                        _ => {}
                    }
                }
            }
        }
        self.save();
        false
    }
    fn mouse(&mut self, m: event::MouseEvent) {
        self.hover = Some((m.column, m.row));
        if self.palette.is_some() {
            return;
        }
        match m.kind {
            MouseEventKind::Down(MouseButton::Left) => {
                self.row_press = None;
                let rects: Vec<_> = self.windows.iter().map(|w| w.rect).collect();
                if let Some(i) = window::topmost(&rects, m.column, m.row) {
                    let w = self.windows.remove(i);
                    let action = window::hit(w.rect, m.column, m.row);
                    if action != Some(Hit::Close) {
                        self.windows.push(w);
                        let rect = self.windows.last().unwrap().rect;
                        if action == Some(Hit::Body) {
                            let w = self.windows.last().unwrap();
                            if let Some((row, item)) = self.row_item(w, m.column, m.row) {
                                self.row_press = Some(RowPress {
                                    press: interaction::Press {
                                        x: m.column,
                                        y: m.row,
                                        moved: false,
                                    },
                                    window: w.id,
                                    row,
                                    item,
                                    shift: m.modifiers.contains(KeyModifiers::SHIFT),
                                });
                            }
                        }
                        if action == Some(Hit::Body)
                            && self.windows.last().is_some_and(|w| w.view == "Hermes chat")
                        {
                            if m.row == rect.y + 2 {
                                let target = if self.chat.target == "hermes" {
                                    "codex"
                                } else {
                                    "hermes"
                                };
                                self.switch_target(target);
                            } else {
                                self.chat.editing = true;
                            }
                        }
                        if action == Some(Hit::Body)
                            && self.windows.last().is_some_and(|w| w.view == "Jobs")
                        {
                            let relative = m.row.saturating_sub(rect.y);
                            if (3..9).contains(&relative) {
                                let rows = self.rows("jobs");
                                let selected = rows
                                    .iter()
                                    .position(|r| r["id"] == self.selected_job)
                                    .unwrap_or(0);
                                let id = rows
                                    .get(selected.saturating_sub(4) + (relative - 3) as usize)
                                    .and_then(|r| r["id"].as_str())
                                    .map(str::to_string);
                                if let Some(id) = id {
                                    self.choose_job(id);
                                }
                            }
                        }
                        if matches!(action, Some(Hit::Title | Hit::Resize(_)))
                            || action == Some(Hit::Body)
                                && self
                                    .windows
                                    .last()
                                    .is_some_and(|w| w.view == "Candlestick chart")
                        {
                            self.drag = Some(Drag {
                                rect,
                                x: m.column,
                                y: m.row,
                                resize: match action {
                                    Some(Hit::Resize(h)) => Some(h),
                                    _ => None,
                                },
                                pan: action == Some(Hit::Body),
                                offset: self.windows.last().unwrap().options["offset"]
                                    .as_u64()
                                    .unwrap_or(0) as usize,
                            });
                        }
                    } else {
                        self.closed.push(vec![w]);
                    }
                    self.save();
                }
            }
            MouseEventKind::Down(MouseButton::Right) => {
                let rects: Vec<_> = self.windows.iter().map(|w| w.rect).collect();
                if let Some(i) = window::topmost(&rects, m.column, m.row) {
                    if self.windows[i].view == "Candlestick chart" {
                        let w = self.windows.remove(i);
                        self.windows.push(w);
                        self.palette = Some("Scale: ".into());
                        self.palette_index = 0;
                        self.search_changed();
                    }
                }
            }
            MouseEventKind::Drag(MouseButton::Left) => {
                if let Some(p) = &mut self.row_press {
                    p.press.motion(m.column, m.row);
                }
                if let (Some(d), Some(w)) = (&self.drag, self.windows.last_mut()) {
                    let (dx, dy) = (m.column as i32 - d.x as i32, m.row as i32 - d.y as i32);
                    if d.pan {
                        let bars = w.options["bars"].as_u64().unwrap_or(80).max(10) as i32;
                        let delta = dx * bars / (w.rect.w.saturating_sub(14).max(1) as i32);
                        w.set("offset", (d.offset as i32 + delta).max(0) as u64);
                        return;
                    }
                    w.rect = if let Some(handle) = d.resize {
                        window::resize_handle(d.rect, handle, dx, dy, self.width, self.height)
                    } else {
                        window::translate(d.rect, dx, dy, self.width, self.height)
                    };
                }
            }
            MouseEventKind::Up(MouseButton::Left) => {
                if self.drag.is_none() {
                    if let Some(p) = self
                        .row_press
                        .take()
                        .filter(|p| p.press.released(m.column, m.row))
                    {
                        if let Some(w) = self.windows.iter_mut().find(|w| w.id == p.window) {
                            w.set("selected_row", p.row as u64);
                            w.set("selected_item", p.item);
                        }
                        let double = self.pending_click.as_ref().is_some_and(|c| {
                            c.at.elapsed() < Duration::from_millis(300)
                                && c.selection.window == p.window
                                && c.selection.item == p.item
                                && c.selection.press.x.abs_diff(p.press.x) < 2
                                && c.selection.press.y.abs_diff(p.press.y) < 2
                        });
                        if double {
                            self.pending_click = None;
                            self.chart_click(p, true);
                        } else if p.shift {
                            self.chart_click(p, false);
                        } else {
                            if let Some(old) = self.pending_click.take() {
                                self.chart_click(old.selection, false);
                            }
                            self.pending_click = Some(PendingClick {
                                selection: p,
                                at: Instant::now(),
                            });
                        }
                    }
                }
                self.row_press = None;
                self.drag = None;
                self.drag_scene = None;
                self.save()
            }
            MouseEventKind::ScrollUp | MouseEventKind::ScrollDown => {
                let rects: Vec<_> = self.windows.iter().map(|w| w.rect).collect();
                if let Some(i) = window::topmost(&rects, m.column, m.row) {
                    if self.windows[i].view == "Candlestick chart" {
                        self.zoom_window(i, m.kind == MouseEventKind::ScrollUp);
                        return;
                    }
                    let w = &mut self.windows[i];
                    w.scroll = if (m.kind == MouseEventKind::ScrollUp) == (w.view != "Hermes chat")
                    {
                        w.scroll.saturating_sub(3)
                    } else {
                        w.scroll.saturating_add(3)
                    };
                }
            }
            _ => {}
        }
    }
}
fn val(value: &Value) -> String {
    match value {
        Value::Null => "—".into(),
        Value::String(s) => s.clone(),
        _ => value.to_string(),
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let mut server =
        std::env::var("OSRS_TERM_SERVER").unwrap_or_else(|_| "http://127.0.0.1:8787".into());
    let mut view = None;
    let mut inspect_query = None;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--search" => inspect_query = Some(args.next().ok_or("--search requires query")?),
            "--server" => server = args.next().ok_or("--server requires URL")?,
            "--view" => {
                let v = args.next().ok_or("--view requires name")?;
                view = Some(
                    match v.as_str() {
                        "market" => "Market table",
                        "alchemy" => "Alchemy gaps",
                        "candles" => "Candlestick chart",
                        "jobs" => "Jobs",
                        "movers" => "Movers screener",
                        "models" => "Model results",
                        "collector" => "Collector health",
                        "metrics" => "Metric series",
                        "chat" => "Hermes chat",
                        "TAS" | "QM" | "HCP" | "HMAP" | "MOST" | "EQS" | "COMP" | "AL" => {
                            v.as_str()
                        }
                        _ => return Err("unknown view".into()),
                    }
                    .into(),
                )
            }
            "--help" | "-h" => {
                println!(
                    "osrs-term [--server URL] [--view market|alchemy|candles|jobs|movers|models|collector|metrics|chat]\nServer URL also reads OSRS_TERM_SERVER. / command palette; q quit."
                );
                return Ok(());
            }
            _ => return Err(format!("Unknown option: {arg}").into()),
        }
    }
    if let Some(query) = inspect_query {
        let mut index = search_ui::SearchUi::load();
        if let Ok(path) = std::env::var("OSRS_SEARCH_CATALOGUE") {
            index.catalogue(&serde_json::from_slice::<Value>(&fs::read(path)?)?);
        }
        index.filter = search::parse(&query).map_err(io::Error::other)?;
        index.rank();
        let results:Vec<_>=index.hits.iter().take(8).map(|h|{let e=&index.entries[h.entry];serde_json::json!({"name":e.name,"key":e.key,"scope":e.scope.name(),"score":h.score,"reason":h.reason,"matched":e.targets[h.target].label,"indices":h.indices})}).collect();
        println!(
            "{}",
            serde_json::to_string_pretty(
                &serde_json::json!({"filter":index.filter,"results":results})
            )?
        );
        return Ok(());
    }
    server = server.trim_end_matches('/').to_string();
    let (tx, mut rx) = mpsc::unbounded_channel();
    let commands = net::connect(server.clone(), tx);
    let mut app = App::new(server, view, commands);
    enable_raw_mode()?;
    let _screen = Screen;
    execute!(io::stdout(), EnterAlternateScreen, EnableMouseCapture)?;
    let bytes = std::sync::Arc::new(std::sync::atomic::AtomicU64::new(0));
    let mut profiler = profile::Profile::new();
    let mut terminal = Terminal::new(CrosstermBackend::new(profile::CountWriter(bytes.clone())))?;
    // Restore the terminal even if a rendering panic occurs.
    let previous = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let _ = disable_raw_mode();
        let _ = execute!(io::stdout(), DisableMouseCapture, LeaveAlternateScreen);
        previous(info);
    }));
    let frame_time = Duration::from_micros(16_667);
    let mut next_frame = Instant::now();
    let mut last_draw = Instant::now();
    let mut dirty = true;
    let mut motion = None;
    'running: loop {
        while let Ok(message) = rx.try_recv() {
            dirty = true;
            match message {
                net::Message::Catalogue(entries) => {
                    app.search.entries.retain(|e| {
                        e.scope != search::Scope::Items && e.scope != search::Scope::Docs
                    });
                    app.search.entries.extend(entries);
                    if app.palette.is_some() {
                        app.search.rank();
                    }
                }
                net::Message::Search(query, kind, value) => app.search_response(query, kind, value),
                net::Message::Data(key, value) => {
                    if key == "search/catalogue" {
                        app.search.catalogue(&value);
                        if app.palette.is_some() {
                            app.search_changed();
                        }
                    }
                    if key == "jobs" {
                        app.search
                            .entries
                            .retain(|e| e.scope != search::Scope::Jobs);
                        if let Some(rows) = value["data"].as_array() {
                            for row in rows {
                                let id = row["id"].as_str().unwrap_or("");
                                app.search.entries.push(search::Entry::new(
                                    format!("job:{id}"),
                                    format!(
                                        "{} {} {}",
                                        row["kind"].as_str().unwrap_or("job"),
                                        id,
                                        row["status"].as_str().unwrap_or("")
                                    ),
                                    search::Scope::Jobs,
                                    row.clone(),
                                ));
                            }
                        }
                        if app.palette.is_some() {
                            app.search.rank();
                        }
                    }
                    if key == "chat" && value["id"].as_str() != Some(app.chat.id.as_str()) {
                        continue;
                    }
                    if key == "chat" {
                        app.sync_chat_config(&value);
                    }
                    if key == "health" {
                        app.connected = true;
                    }
                    if key == "jobs"
                        && (app.selected_job.is_empty()
                            || !value["data"].as_array().is_some_and(|rows| {
                                rows.iter().any(|r| r["id"] == app.selected_job)
                            }))
                    {
                        if let Some(id) = value["data"][0]["id"].as_str() {
                            app.choose_job(id.into());
                        }
                    }
                    if key == "chats" && app.chat.id.is_empty() && !app.chat.fresh {
                        if let Some(id) = value["data"][0]["id"].as_str() {
                            app.choose_chat(id.into());
                        }
                    }
                    let mut value = value;
                    if key == "chat_progress" {
                        let old = app
                            .data
                            .get(&key)
                            .and_then(|v| v["text"].as_str())
                            .unwrap_or("");
                        let mut text = format!("{}{}", old, value["text"].as_str().unwrap_or(""));
                        if text.len() > 65536 {
                            let mut start = text.len() - 65536;
                            while !text.is_char_boundary(start) {
                                start += 1;
                            }
                            text = text[start..].into();
                        }
                        value["text"] = text.into();
                    }
                    app.received.insert(key.clone(), Instant::now());
                    app.data.insert(key, value);
                }
                net::Message::ChatStarted(value) => {
                    app.chat.pending = false;
                    if let Some(id) = value["id"].as_str() {
                        app.chat.id = id.into();
                        let _ = app.commands.send(net::Command::ChatWatch(id.into()));
                    }
                    app.sync_chat_config(&value);
                    app.data.insert("chat".into(), value);
                    app.save();
                }
                net::Message::Started(job) => {
                    if let Some(id) = job["id"].as_str() {
                        app.choose_job(id.into());
                    }
                    app.errors
                        .push(format!("Queued {} job {}", job["kind"], job["id"]));
                }
                net::Message::Stream(state) => app.stream_state = state,
                net::Message::Event(id, event) => {
                    let events = app.job_events.entry(id.clone()).or_default();
                    if !events.iter().any(|e| e["seq"] == event["seq"]) {
                        if event["type"] == "status" {
                            if let Some(rows) = app
                                .data
                                .get_mut("jobs")
                                .and_then(|v| v["data"].as_array_mut())
                            {
                                for row in rows {
                                    if row["id"] == id {
                                        row["status"] = event["data"]["status"].clone();
                                    }
                                }
                            }
                        }
                        events.push(event);
                    }
                }
                net::Message::Error(key, error) => {
                    if key.starts_with("chat") {
                        if key == "chat send" {
                            app.chat.pending = false;
                            app.chat.errors.push(error.clone());
                        } else if key == "chat cancel" {
                            app.chat.errors.push(error.clone());
                        }
                    }
                    if key == "health" {
                        app.connected = false;
                    }
                    if key.starts_with("terminal:") && !app.data.contains_key(&key) {
                        app.data
                            .insert(key.clone(), serde_json::json!({"error":error,"stale":true}));
                    }
                    if let Some(value) = app.data.get_mut(&key) {
                        value["stale"] = true.into();
                        value["error"] = error.clone().into();
                    }
                    app.errors.push(format!("{key}: {error}"));
                    if app.errors.len() > 500 {
                        app.errors.remove(0);
                    }
                }
            }
        }
        dirty |= app.flush_click();
        let size = terminal.size()?;
        if app.width != size.width || app.height != size.height.saturating_sub(2) {
            app.clamp(size.width, size.height);
        }
        if Instant::now() >= next_frame && (dirty || last_draw.elapsed() >= Duration::from_secs(1))
        {
            if let Some(m) = motion.take() {
                app.mouse(m);
            }
            if app.drag.is_none() {
                app.sync_terminal();
            }
            let started = Instant::now();
            let before = bytes.load(std::sync::atomic::Ordering::Relaxed);
            terminal.draw(|f| app.draw(f))?;
            profiler.frame(
                started,
                bytes.load(std::sync::atomic::Ordering::Relaxed) - before,
                app.hover,
                app.drag.is_some(),
            );
            last_draw = Instant::now();
            next_frame = last_draw + frame_time;
            dirty = false;
        }
        let timeout = if dirty {
            next_frame.saturating_duration_since(Instant::now())
        } else {
            Duration::from_millis(50)
        };
        if !event::poll(timeout)? {
            continue;
        }
        let batch_start = Instant::now();
        loop {
            let input = event::read()?;
            if let Event::Mouse(m) = input {
                profiler.events += 1;
                profiler.pending += 1;
                if matches!(m.kind, MouseEventKind::Moved | MouseEventKind::Drag(_)) {
                    motion = Some(m);
                    dirty = dirty
                        || app.drag.is_some()
                        || app
                            .windows
                            .last()
                            .is_some_and(|w| w.view == "Candlestick chart");
                } else {
                    if let Some(last) = motion.take() {
                        app.mouse(last);
                    }
                    app.mouse(m);
                    app.cache_drag();
                    dirty = true;
                }
            } else {
                if let Some(last) = motion.take() {
                    app.mouse(last);
                }
                app.drag_scene = None;
                match input {
                    Event::Key(k) if k.kind == event::KeyEventKind::Press => {
                        if k.code == KeyCode::Char('c')
                            && k.modifiers.contains(KeyModifiers::CONTROL)
                            && !(app.chat.editing
                                && app.windows.last().is_some_and(|w| w.view == "Hermes chat"))
                            || app.key(k.code, k.modifiers)
                        {
                            app.save();
                            break 'running;
                        }
                        dirty = true;
                    }
                    Event::Resize(w, h) => {
                        app.drag = None;
                        app.clamp(w, h);
                        app.save();
                        dirty = true;
                    }
                    _ => {}
                }
            }
            // Bound input processing too, so continuous input cannot starve rendering.
            if batch_start.elapsed() >= Duration::from_millis(2) || !event::poll(Duration::ZERO)? {
                break;
            }
        }
    }

    Ok(())
}
