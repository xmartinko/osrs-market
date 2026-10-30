mod net;
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

const VIEWS: &[&str] = &["Market table", "Alchemy gaps"];
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
    fn new(server: String, view: Option<String>) -> Self {
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
        Self {
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
            server,
        }
    }
    fn save(&mut self) {
        let path = layout_path();
        let result = (|| -> io::Result<()> {
            fs::create_dir_all(path.parent().unwrap())?;
            fs::write(
                path.with_extension("tmp"),
                serde_json::to_vec_pretty(&self.windows)?,
            )?;
            fs::rename(path.with_extension("tmp"), path)
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
                    x: 4 + n * 2,
                    y: 2 + n,
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
        let help = if self.filtering {
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
            let height = 16.min(area.height);
            let rect = Rect::new(
                area.width.saturating_sub(width) / 2,
                area.height.saturating_sub(height) / 2,
                width,
                height,
            );
            f.render_widget(Clear, rect);
            let matches: Vec<_> = VIEWS.iter().filter(|v| window::fuzzy(query, v)).collect();
            let mut lines = vec![Line::from(format!(" > {query}_")), Line::from("")];
            for (i, name) in matches.iter().enumerate() {
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
            Rect::new(area.x, area.y + 1, area.width, area.height - 1),
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
            Rect::new(area.x, area.y + 2, area.width, area.height - 2),
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
                    let selected = VIEWS
                        .iter()
                        .filter(|v| window::fuzzy(query, v))
                        .nth(self.palette_index)
                        .map(|s| s.to_string());
                    self.palette = None;
                    if let Some(v) = selected {
                        self.add(v)
                    }
                }
                _ => {}
            }
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
                    w.scroll = if m.kind == MouseEventKind::ScrollUp {
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
                        _ => return Err("unknown view".into()),
                    }
                    .into(),
                )
            }
            "--help" | "-h" => {
                println!(
                    "osrs-term [--server URL] [--view market|alchemy]\nServer URL also reads OSRS_TERM_SERVER. / command palette; q quit."
                );
                return Ok(());
            }
            _ => return Err(format!("Unknown option: {arg}").into()),
        }
    }
    server = server.trim_end_matches('/').to_string();
    let (tx, mut rx) = mpsc::unbounded_channel();
    net::connect(server.clone(), tx);
    let mut app = App::new(server, view);
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
                    if key == "health" {
                        app.connected = true;
                    }
                    app.received.insert(key.clone(), Instant::now());
                    app.data.insert(key, value);
                }
                net::Message::Error(key, error) => {
                    if key == "health" {
                        app.connected = false;
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
                    if k.code == KeyCode::Char('c') && k.modifiers.contains(KeyModifiers::CONTROL)
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
