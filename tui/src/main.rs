mod charts;
mod chat;
mod net;
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
    "Hermes chat",
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
    resize: bool,
}
struct App {
    windows: Vec<Window>,
    data: HashMap<String, Value>,
    received: HashMap<String, Instant>,
    connected: bool,
    errors: Vec<String>,
    palette: Option<String>,
    palette_index: usize,
    filtering: bool,
    drag: Option<Drag>,
    width: u16,
    height: u16,
    server: String,
    commands: mpsc::UnboundedSender<net::Command>,
    item: u64,
    tf: String,
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
        let windows = if let Some(view) = view {
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
            }]
        } else {
            fs::read(layout_path())
                .ok()
                .and_then(|s| serde_json::from_slice::<Vec<Window>>(&s).ok())
                .filter(|w| !w.is_empty())
                .unwrap_or_else(|| {
                    vec![
                        Window {
                            view: "Market table".into(),
                            rect: Bounds {
                                x: 1,
                                y: 1,
                                w: 116,
                                h: 34,
                            },
                            scroll: 0,
                            filter: String::new(),
                            sort: 0,
                        },
                        Window {
                            view: "Alchemy gaps".into(),
                            rect: Bounds {
                                x: 70,
                                y: 25,
                                w: 118,
                                h: 16,
                            },
                            scroll: 0,
                            filter: String::new(),
                            sort: 0,
                        },
                    ]
                })
        };
        let state: Value = fs::read(layout_path().with_file_name("state.json"))
            .ok()
            .and_then(|v| serde_json::from_slice(&v).ok())
            .unwrap_or(Value::Null);
        let app = Self {
            windows,
            data: HashMap::new(),
            received: HashMap::new(),
            connected: false,
            errors: vec![],
            palette: None,
            palette_index: 0,
            filtering: false,
            drag: None,
            width: 0,
            height: 0,
            server: server.clone(),
            commands,
            item: state["item"].as_u64().unwrap_or(855),
            tf: state["tf"]
                .as_str()
                .filter(|s| ["5m", "1h", "1d"].contains(s))
                .unwrap_or("5m")
                .into(),
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
        app.history();
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
    fn save(&mut self) {
        let path = layout_path();
        let result = (|| -> io::Result<()> {
            fs::create_dir_all(path.parent().unwrap())?;
            fs::write(
                path.with_extension("tmp"),
                serde_json::to_vec_pretty(&self.windows)?,
            )?;
            fs::rename(path.with_extension("tmp"), &path)?;
            let state = serde_json::json!({"item":self.item,"tf":self.tf,"selected_job":self.selected_job,"metric":self.metric,"dataset":self.dataset,"track":self.track,"preset":self.preset,"horizon":self.horizon,"chat_id":self.chat.id,"chat_server":self.server});
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
        });
        self.save();
    }
    fn history(&self) {
        let _ = self
            .commands
            .send(net::Command::History(self.item, self.tf.clone()));
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
        if action == "Chat: new conversation" {
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
        let mut rows = self.rows("prices/latest");
        rows.retain(|r| {
            r["name"]
                .as_str()
                .unwrap_or("")
                .to_lowercase()
                .contains(&w.filter.to_lowercase())
        });
        if w.sort == 1 {
            rows.sort_by(|a, b| b["margin_gp"].as_i64().cmp(&a["margin_gp"].as_i64()));
        }
        if w.sort == 2 {
            rows.sort_by(|a, b| b["buy_price"].as_i64().cmp(&a["buy_price"].as_i64()));
        }
        rows
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
        let area = f.area();
        f.render_widget(Block::default().style(Style::default().bg(BG).fg(FG)), area);
        if self.windows.is_empty() {
            f.render_widget(
                Paragraph::new("  OSRS TERM   / opens the command palette")
                    .style(Style::default().fg(ACCENT)),
                area,
            );
        }
        for (i, w) in self.windows.iter().enumerate() {
            let r = Rect::new(w.rect.x, w.rect.y, w.rect.w, w.rect.h);
            let focus = i + 1 == self.windows.len();
            f.render_widget(Clear, r);
            let block = Block::default()
                .borders(Borders::ALL)
                .title(format!(" {} {} ", if focus { "◆" } else { "◇" }, w.view))
                .border_style(Style::default().fg(if focus { ACCENT } else { Color::DarkGray }))
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
                "Market table" => self.market(f, inner, w),
                "Alchemy gaps" => self.alchemy(f, inner, w),
                "Candlestick chart" => self.candles(f, inner, w),
                "Metric series" => charts::line(f, inner, &self.metric_points(), &self.metric),
                "Jobs" => self.jobs(f, inner, w),
                "Hermes chat" => self.chat_view(f, inner, w),
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
            self.freshness("prices/latest")
        );
        f.render_widget(
            Paragraph::new(status).style(Style::default().bg(Color::Rgb(23, 40, 51)).fg(ACCENT)),
            Rect::new(0, area.height.saturating_sub(2), area.width, 1),
        );
        let help = if self.windows.last().is_some_and(|w| w.view == "Hermes chat")
            && self.chat.editing
        {
            " Enter send  Alt+Enter/Ctrl+J newline  Ctrl+X cancel  Esc leave input  Ctrl+P palette  Tab focus  Ctrl+W close"
        } else if self.filtering {
            " Filter: type text · Enter finish · Esc clear"
        } else {
            " / palette  Tab focus  arrows move  Shift+arrows resize  Ctrl+W close  m maximize  f filter  s sort  j/k scroll  q/Esc quit"
        };
        f.render_widget(
            Paragraph::new(help).style(Style::default().fg(Color::Gray)),
            Rect::new(0, area.height.saturating_sub(1), area.width, 1),
        );
        if let Some(query) = &self.palette {
            let width = 70.min(area.width);
            let height = 30.min(area.height);
            let rect = Rect::new(
                area.width.saturating_sub(width) / 2,
                area.height.saturating_sub(height) / 2,
                width,
                height,
            );
            f.render_widget(Clear, rect);
            let matches: Vec<_> = VIEWS.iter().filter(|v| window::fuzzy(query, v)).collect();
            let mut lines = vec![
                Line::from(format!(" > {query}_")),
                Line::from(format!(
                    " dataset:{} track:{} {}h",
                    self.dataset, self.track, self.horizon
                )),
                Line::from(" Or type: item 4151 / metric net_gp"),
                Line::from(""),
            ];
            for (i, name) in matches
                .iter()
                .enumerate()
                .skip(self.palette_index.saturating_sub(19))
                .take(22)
            {
                lines.push(Line::styled(
                    format!(
                        " {} {name}",
                        if i == self.palette_index { "▶" } else { " " }
                    ),
                    Style::default().fg(if i == self.palette_index { ACCENT } else { FG }),
                ));
            }
            f.render_widget(
                Paragraph::new(lines)
                    .block(
                        Block::default()
                            .borders(Borders::ALL)
                            .title(" Command palette "),
                    )
                    .style(Style::default().bg(BG).fg(FG)),
                rect,
            );
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
                Style::default().fg(if r["margin_gp"].as_i64().unwrap_or(0) > 0 {
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
        if let Some(query) = &mut self.palette {
            match code {
                KeyCode::Esc => self.palette = None,
                KeyCode::Char(c) => {
                    query.push(c);
                    self.palette_index = 0
                }
                KeyCode::Backspace => {
                    query.pop();
                    self.palette_index = 0
                }
                KeyCode::Down => {
                    let n = VIEWS.iter().filter(|v| window::fuzzy(query, v)).count();
                    self.palette_index = (self.palette_index + 1).min(n.saturating_sub(1));
                }
                KeyCode::Up => self.palette_index = self.palette_index.saturating_sub(1),
                KeyCode::Enter => {
                    if let Some(value) = query
                        .strip_prefix("item ")
                        .and_then(|s| s.trim().parse::<u64>().ok())
                        .filter(|i| *i > 0)
                    {
                        self.item = value;
                        self.data.remove("history");
                        self.history();
                        self.palette = None;
                        self.add("Candlestick chart".into());
                        return false;
                    }
                    if let Some(value) = query
                        .strip_prefix("metric ")
                        .map(str::trim)
                        .filter(|s| !s.is_empty())
                    {
                        self.metric = value.into();
                        self.palette = None;
                        self.add("Metric series".into());
                        return false;
                    }
                    let selected = VIEWS
                        .iter()
                        .filter(|v| window::fuzzy(query, v))
                        .nth(self.palette_index)
                        .map(|s| s.to_string());
                    self.palette = None;
                    if let Some(v) = selected {
                        self.action(v)
                    }
                }
                _ => {}
            }
            return false;
        }
        if self.windows.last().is_some_and(|w| w.view == "Hermes chat")
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
        if code == KeyCode::Char('/')
            || code == KeyCode::Char('p') && modifiers.contains(KeyModifiers::CONTROL)
        {
            self.palette = Some(String::new());
            self.palette_index = 0;
            return false;
        }
        let focused = self.windows.last().map(|w| w.view.as_str()).unwrap_or("");
        if focused == "Candlestick chart" {
            if let KeyCode::Char(c @ ('1' | '2' | '3')) = code {
                self.tf = match c {
                    '1' => "5m",
                    '2' => "1h",
                    _ => "1d",
                }
                .into();
                self.data.remove("history");
                if let Some(w) = self.windows.last_mut() {
                    w.scroll = 0;
                }
                self.history();
                self.save();
                return false;
            }
        }
        if focused == "Market table" && code == KeyCode::Enter {
            if let Some(w) = self.windows.last() {
                if let Some(id) = self
                    .market_rows(w)
                    .get(w.scroll)
                    .and_then(|r| r["item_id"].as_u64())
                {
                    self.item = id;
                    self.data.remove("history");
                    self.history();
                    self.add("Candlestick chart".into());
                }
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
            KeyCode::Char('q') | KeyCode::Esc => return true,
            KeyCode::Tab => {
                if self.windows.len() > 1 {
                    let w = self.windows.remove(0);
                    self.windows.push(w);
                }
            }
            KeyCode::Char('w') if modifiers.contains(KeyModifiers::CONTROL) => {
                self.windows.pop();
            }
            KeyCode::Char('f') => self.filtering = true,
            _ => {
                if let Some(w) = self.windows.last_mut() {
                    match code {
                        KeyCode::Char('s') => w.sort = (w.sort + 1) % 3,
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
                            w.rect = if modifiers.contains(KeyModifiers::SHIFT) {
                                window::resize(w.rect, dx, dy, self.width, self.height)
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
                let rects: Vec<_> = self.windows.iter().map(|w| w.rect).collect();
                if let Some(i) = window::topmost(&rects, m.column, m.row) {
                    let w = self.windows.remove(i);
                    let action = window::hit(w.rect, m.column, m.row);
                    if action != Some(Hit::Close) {
                        self.windows.push(w);
                        let rect = self.windows.last().unwrap().rect;
                        if action == Some(Hit::Body)
                            && self.windows.last().is_some_and(|w| w.view == "Hermes chat")
                        {
                            self.chat.editing = true;
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
                        if matches!(action, Some(Hit::Title | Hit::Resize)) {
                            self.drag = Some(Drag {
                                rect,
                                x: m.column,
                                y: m.row,
                                resize: action == Some(Hit::Resize),
                            });
                        }
                    }
                    self.save();
                }
            }
            MouseEventKind::Drag(MouseButton::Left) => {
                if let (Some(d), Some(w)) = (&self.drag, self.windows.last_mut()) {
                    let (dx, dy) = (m.column as i32 - d.x as i32, m.row as i32 - d.y as i32);
                    w.rect = if d.resize {
                        window::resize(d.rect, dx, dy, self.width, self.height)
                    } else {
                        window::translate(d.rect, dx, dy, self.width, self.height)
                    };
                }
            }
            MouseEventKind::Up(MouseButton::Left) => {
                self.drag = None;
                self.save()
            }
            MouseEventKind::ScrollUp | MouseEventKind::ScrollDown => {
                let rects: Vec<_> = self.windows.iter().map(|w| w.rect).collect();
                if let Some(i) = window::topmost(&rects, m.column, m.row) {
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
    while let Some(arg) = args.next() {
        match arg.as_str() {
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
    server = server.trim_end_matches('/').to_string();
    let (tx, mut rx) = mpsc::unbounded_channel();
    let commands = net::connect(server.clone(), tx);
    let mut app = App::new(server, view, commands);
    enable_raw_mode()?;
    let _screen = Screen;
    execute!(io::stdout(), EnterAlternateScreen, EnableMouseCapture)?;
    let mut terminal = Terminal::new(CrosstermBackend::new(io::stdout()))?;
    // Restore the terminal even if a rendering panic occurs.
    let previous = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let _ = disable_raw_mode();
        let _ = execute!(io::stdout(), DisableMouseCapture, LeaveAlternateScreen);
        previous(info);
    }));
    loop {
        while let Ok(message) = rx.try_recv() {
            match message {
                net::Message::Data(key, value) => {
                    if key == "chat" && value["id"].as_str() != Some(app.chat.id.as_str()) {
                        continue;
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
                    app.received.insert(key.clone(), Instant::now());
                    app.data.insert(key, value);
                }
                net::Message::ChatStarted(value) => {
                    app.chat.pending = false;
                    if let Some(id) = value["id"].as_str() {
                        app.chat.id = id.into();
                        let _ = app.commands.send(net::Command::ChatWatch(id.into()));
                    }
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
        let size = terminal.size()?;
        if app.width != size.width || app.height != size.height.saturating_sub(2) {
            app.clamp(size.width, size.height);
        }
        terminal.draw(|f| app.draw(f))?;
        if event::poll(Duration::from_millis(100))? {
            match event::read()? {
                Event::Key(k) if k.kind == event::KeyEventKind::Press => {
                    if k.code == KeyCode::Char('c')
                        && k.modifiers.contains(KeyModifiers::CONTROL)
                        && !(app.chat.editing
                            && app.windows.last().is_some_and(|w| w.view == "Hermes chat"))
                        || app.key(k.code, k.modifiers)
                    {
                        app.save();
                        break;
                    }
                }
                Event::Mouse(m) => app.mouse(m),
                Event::Resize(w, h) => {
                    app.clamp(w, h);
                    app.save()
                }
                _ => {}
            }
        }
    }
    Ok(())
}
