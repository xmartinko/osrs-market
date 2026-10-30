use super::*;

pub struct ChatUi {
    pub id: String,
    pub input: String,
    pub cursor: usize,
    pub editing: bool,
    pub pending: bool,
    pub fresh: bool,
    pub errors: Vec<String>,
    submitted: Option<Instant>,
}
impl ChatUi {
    pub fn new(state: &Value, server: &str) -> Self {
        let id = std::env::var("OSRS_TERM_CHAT_ID").unwrap_or_else(|_| {
            if state["chat_server"] == server {
                state["chat_id"].as_str().unwrap_or("").into()
            } else {
                String::new()
            }
        });
        Self {
            id,
            input: String::new(),
            cursor: 0,
            editing: true,
            pending: false,
            fresh: false,
            errors: vec![],
            submitted: None,
        }
    }
    fn insert(&mut self, c: char) {
        // Match server's 16,000-character maximum; preserve UTF-8 boundaries.
        if self.input.chars().count() < 16000 {
            self.input.insert(self.cursor, c);
            self.cursor += c.len_utf8();
        }
    }
}

fn safe_text(text: &str) -> String {
    text.chars()
        .filter(|c| !c.is_control() || *c == '\n' || *c == '\t')
        .collect::<String>()
        .replace('\t', "    ")
}
fn wrapped(text: &str, width: u16) -> Vec<String> {
    let width = usize::from(width.max(1));
    let mut result = vec![];
    for line in safe_text(text).split('\n') {
        let mut part = String::new();
        let mut used = 0;
        for c in line.chars() {
            let size = Span::raw(c.to_string()).width();
            if used + size > width && !part.is_empty() {
                result.push(std::mem::take(&mut part));
                used = 0;
            }
            part.push(c);
            used += size;
        }
        result.push(part);
    }
    result
}
fn money(value: Option<f64>) -> String {
    value
        .map(|n| format!("${n:.4}"))
        .unwrap_or_else(|| "—".into())
}

impl App {
    pub fn choose_chat(&mut self, id: String) {
        self.chat.id = id.clone();
        self.chat.fresh = false;
        self.chat.errors.clear();
        self.data.remove("chat");
        self.data.remove("chat_progress");
        let _ = self.commands.send(net::Command::ChatWatch(id));
        self.save();
    }
    pub fn new_chat(&mut self) {
        if self.chat.pending
            || self
                .data
                .get("chat")
                .is_some_and(|v| v["status"] == "running")
        {
            self.chat
                .errors
                .push("Cancel or finish the running turn before starting a new chat".into());
            return;
        }
        let _ = self.commands.send(net::Command::ChatWatch(String::new()));
        self.chat.id.clear();
        self.chat.fresh = true;
        self.chat.editing = true;
        self.chat.errors.clear();
        self.data.remove("chat");
        self.data.remove("chat_progress");
        if !self.windows.last().is_some_and(|w| w.view == "Hermes chat") {
            self.add("Hermes chat".into());
        }
        self.save();
    }
    pub fn next_chat(&mut self) {
        let rows = self.rows("chats");
        let pos = rows
            .iter()
            .position(|r| r["id"] == self.chat.id)
            .unwrap_or(0);
        let next = rows
            .get((pos + 1) % rows.len().max(1))
            .and_then(|r| r["id"].as_str())
            .map(str::to_string);
        if let Some(id) = next {
            self.choose_chat(id);
        }
        if !self.windows.last().is_some_and(|w| w.view == "Hermes chat") {
            self.add("Hermes chat".into());
        }
    }
    pub fn chat_key(&mut self, code: KeyCode, modifiers: KeyModifiers) -> bool {
        let running = self.chat.pending
            || self
                .data
                .get("chat")
                .is_some_and(|v| v["status"] == "running");
        if modifiers.contains(KeyModifiers::CONTROL) {
            match code {
                KeyCode::Char('c' | 'x') => {
                    if !self.chat.id.is_empty() && running {
                        let _ = self
                            .commands
                            .send(net::Command::ChatCancel(self.chat.id.clone()));
                    }
                    return true;
                }
                KeyCode::Char('j') if self.chat.editing => {
                    self.chat.insert('\n');
                    return true;
                }
                KeyCode::Char('p' | 'w') => return false,
                _ => {}
            }
        }
        if code == KeyCode::Esc {
            self.chat.editing = false;
            return true;
        }
        if !self.chat.editing {
            if matches!(code, KeyCode::Enter | KeyCode::Char('i')) {
                self.chat.editing = true;
                return true;
            }
            return false;
        }
        match code {
            KeyCode::Enter if modifiers.contains(KeyModifiers::ALT) => self.chat.insert('\n'),
            KeyCode::Enter => {
                if !self.chat.input.trim().is_empty() {
                    if running {
                        self.chat
                            .errors
                            .push("Busy: wait for this turn or press Ctrl+X to cancel".into());
                    } else {
                        let mut request = serde_json::json!({"text":self.chat.input});
                        if !self.chat.id.is_empty() {
                            request["chat_id"] = self.chat.id.clone().into();
                        }
                        let _ = self.commands.send(net::Command::ChatSend(request));
                        self.chat.pending = true;
                        self.chat.submitted = Some(Instant::now());
                        self.chat.input.clear();
                        self.chat.cursor = 0;
                        self.data.remove("chat_progress");
                        if let Some(w) = self.windows.last_mut() {
                            w.scroll = 0;
                        }
                    }
                }
            }
            KeyCode::Char(c) if !modifiers.contains(KeyModifiers::CONTROL) && !c.is_control() => {
                self.chat.insert(c)
            }
            KeyCode::Backspace if self.chat.cursor > 0 => {
                let previous = self.chat.input[..self.chat.cursor]
                    .char_indices()
                    .last()
                    .unwrap()
                    .0;
                self.chat.input.drain(previous..self.chat.cursor);
                self.chat.cursor = previous;
            }
            KeyCode::Delete if self.chat.cursor < self.chat.input.len() => {
                let next = self.chat.input[self.chat.cursor..]
                    .chars()
                    .next()
                    .unwrap()
                    .len_utf8();
                self.chat
                    .input
                    .drain(self.chat.cursor..self.chat.cursor + next);
            }
            KeyCode::Left => {
                self.chat.cursor = self.chat.input[..self.chat.cursor]
                    .char_indices()
                    .last()
                    .map(|(i, _)| i)
                    .unwrap_or(0);
            }
            KeyCode::Right if self.chat.cursor < self.chat.input.len() => {
                self.chat.cursor += self.chat.input[self.chat.cursor..]
                    .chars()
                    .next()
                    .unwrap()
                    .len_utf8();
            }
            KeyCode::Home => {
                self.chat.cursor = self.chat.input[..self.chat.cursor]
                    .rfind('\n')
                    .map(|i| i + 1)
                    .unwrap_or(0);
            }
            KeyCode::End => {
                self.chat.cursor += self.chat.input[self.chat.cursor..]
                    .find('\n')
                    .unwrap_or(self.chat.input.len() - self.chat.cursor);
            }
            KeyCode::Up => {
                let start = self.chat.input[..self.chat.cursor]
                    .rfind('\n')
                    .map(|i| i + 1)
                    .unwrap_or(0);
                if start > 0 {
                    let previous = self.chat.input[..start - 1]
                        .rfind('\n')
                        .map(|i| i + 1)
                        .unwrap_or(0);
                    let column = self.chat.input[start..self.chat.cursor].chars().count();
                    self.chat.cursor = previous
                        + self.chat.input[previous..start - 1]
                            .char_indices()
                            .nth(column)
                            .map(|(i, _)| i)
                            .unwrap_or(start - 1 - previous);
                }
            }
            KeyCode::Down => {
                if let Some(end) = self.chat.input[self.chat.cursor..].find('\n') {
                    let start = self.chat.input[..self.chat.cursor]
                        .rfind('\n')
                        .map(|i| i + 1)
                        .unwrap_or(0);
                    let column = self.chat.input[start..self.chat.cursor].chars().count();
                    let next = self.chat.cursor + end + 1;
                    let next_end = self.chat.input[next..]
                        .find('\n')
                        .map(|i| next + i)
                        .unwrap_or(self.chat.input.len());
                    self.chat.cursor = next
                        + self.chat.input[next..next_end]
                            .char_indices()
                            .nth(column)
                            .map(|(i, _)| i)
                            .unwrap_or(next_end - next);
                }
            }
            KeyCode::Tab => return false,
            _ => {}
        }
        true
    }
    pub fn chat_view(&self, f: &mut Frame, area: Rect, w: &Window) {
        let parts = Layout::vertical([
            Constraint::Length(2),
            Constraint::Length(2),
            Constraint::Length(1),
            Constraint::Min(0),
            Constraint::Length(5),
        ])
        .split(area);
        let null = Value::Null;
        let chat = self.data.get("chat").unwrap_or(&null);
        let session = chat["session"]
            .as_str()
            .unwrap_or("pending first turn / discovery");
        f.render_widget(Paragraph::new(vec![
            Line::from(format!("Hermes session: {session}")),
            Line::styled("Separate Hermes session from other chats • / palette after Esc • Chat: new / next conversation", Style::default().fg(Color::Gray)),
        ]), parts[0]);
        let usage = self.data.get("usage").unwrap_or(&null);
        let percent = usage["percent_remaining"].as_f64().unwrap_or(0.);
        let color = if percent < 10. {
            Color::Red
        } else if percent < 25. {
            Color::Yellow
        } else {
            Color::Green
        };
        let age = usage["timestamp"]
            .as_f64()
            .map(|t| (chrono::Utc::now().timestamp() as f64 - t).max(0.) as u64);
        let stale = !self.connected || usage["stale"] == true || age.is_none_or(|a| a >= 120);
        let credits = if let (Some(remaining), Some(total)) =
            (usage["remaining"].as_f64(), usage["total_credits"].as_f64())
        {
            let full = (percent.clamp(0., 100.) / 10.).round() as usize;
            format!(
                "credits {}{} ${remaining:.2} / ${total:.2} ({percent:.0}%){}",
                "▊".repeat(full),
                "░".repeat(10 - full),
                if stale {
                    format!(" — stale {}m", age.unwrap_or(0) / 60)
                } else {
                    String::new()
                }
            )
        } else {
            "credits — unavailable / stale".into()
        };
        let last = chat["messages"]
            .as_array()
            .and_then(|rows| rows.iter().rev().find(|r| r["role"] == "assistant"))
            .and_then(|r| r["usage"]["cost"].as_f64());
        let spend = format!(
            "today {} • this chat {}{} • last turn {}{}",
            money(usage["usage_daily"].as_f64()),
            money(chat["cost"].as_f64()),
            if chat["cost_incomplete"] == true {
                " (incomplete)"
            } else {
                ""
            },
            money(last),
            usage["error"]
                .as_str()
                .map(|e| format!(" • {e}"))
                .unwrap_or_default()
        );
        f.render_widget(
            Paragraph::new(vec![
                Line::styled(
                    credits,
                    Style::default().fg(if stale { Color::Yellow } else { color }),
                ),
                Line::from(spend),
            ]),
            parts[1],
        );
        let running = self.chat.pending || chat["status"] == "running";
        let status = if running {
            let elapsed = if self.chat.pending {
                self.chat
                    .submitted
                    .map(|t| t.elapsed().as_secs())
                    .unwrap_or(0)
            } else {
                chat["messages"]
                    .as_array()
                    .and_then(|v| v.last())
                    .and_then(|v| v["created_at"].as_f64())
                    .map(|t| (chrono::Utc::now().timestamp() as f64 - t).max(0.) as u64)
                    .unwrap_or(0)
            };
            let spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
                [(chrono::Utc::now().timestamp_millis() / 100) as usize % 10];
            format!("{spinner} thinking • {elapsed}s elapsed • Ctrl+X / Ctrl+C cancel • UI live")
        } else {
            "Ready • Enter sends • Alt+Enter / Ctrl+J newline • Esc leaves input • wheel scrollback"
                .into()
        };
        f.render_widget(
            Paragraph::new(status).style(Style::default().fg(ACCENT)),
            parts[2],
        );
        let mut lines = vec![];
        if let Some(messages) = chat["messages"].as_array() {
            for message in messages {
                let user = message["role"] == "user";
                let text = format!(
                    "{}: {}",
                    if user { "You" } else { "Hermes" },
                    message["text"].as_str().unwrap_or("")
                );
                for line in wrapped(&text, parts[3].width) {
                    lines.push(Line::styled(
                        line,
                        Style::default().fg(if user { ACCENT } else { FG }),
                    ));
                }
                if let Some(error) = message["error"].as_str() {
                    let text = format!(
                        "ERROR: {error} (duration {:.1}s, exit {}, timeout {})",
                        message["duration"].as_f64().unwrap_or(0.),
                        val(&message["exit_code"]),
                        message["timed_out"]
                    );
                    for line in wrapped(&text, parts[3].width) {
                        lines.push(Line::styled(line, Style::default().fg(Color::Red)));
                    }
                }
                lines.push(Line::from(""));
            }
        }
        for error in &self.chat.errors {
            for line in wrapped(&format!("ERROR: {error}"), parts[3].width) {
                lines.push(Line::styled(line, Style::default().fg(Color::Red)));
            }
        }
        if running {
            if let Some(log) = self
                .data
                .get("chat_progress")
                .and_then(|v| v["text"].as_str())
            {
                for line in wrapped(log, parts[3].width) {
                    lines.push(Line::styled(line, Style::default().fg(Color::Gray)));
                }
            }
        }
        let scroll = lines
            .len()
            .saturating_sub(parts[3].height as usize)
            .saturating_sub(w.scroll);
        f.render_widget(
            Paragraph::new(lines).scroll((scroll.min(u16::MAX as usize) as u16, 0)),
            parts[3],
        );
        let input_block = Block::bordered()
            .title(if self.chat.editing {
                " Message • editing "
            } else {
                " Message • Enter / i to edit "
            })
            .border_style(Style::default().fg(if self.chat.editing {
                ACCENT
            } else {
                Color::DarkGray
            }));
        let inner = input_block.inner(parts[4]);
        f.render_widget(input_block, parts[4]);
        let mut input = self.chat.input.clone();
        if self.chat.editing {
            input.insert(self.chat.cursor, '▏');
        }
        let input_lines = wrapped(&input, inner.width);
        let cursor_line = wrapped(&input[..self.chat.cursor], inner.width)
            .len()
            .saturating_sub(1);
        let offset = cursor_line.saturating_sub(inner.height.saturating_sub(1) as usize);
        f.render_widget(
            Paragraph::new(input_lines.into_iter().map(Line::from).collect::<Vec<_>>())
                .scroll((offset.min(u16::MAX as usize) as u16, 0)),
            inner,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn editing_preserves_unicode_and_multiline() {
        let mut ui = ChatUi::new(&Value::Null, "test");
        for c in "hé\n水".chars() {
            ui.insert(c);
        }
        assert_eq!(&ui.input[..ui.cursor], "hé\n水");
        assert_eq!(wrapped("ab水cd\ne", 4), vec!["ab水", "cd", "e"]);
        assert_eq!(safe_text("a\x1b[31m\0b"), "a[31mb");
    }
}

#[cfg(test)]
mod input_tests {
    use super::*;
    #[test]
    fn input_sends_multiline_argv_text_and_stays_cancellable() {
        let (tx, mut rx) = mpsc::unbounded_channel();
        let mut app = App::new("test-chat-input".into(), Some("Hermes chat".into()), tx);
        while rx.try_recv().is_ok() {}
        app.chat.id = "test-id".into();
        for c in "first".chars() {
            assert!(app.chat_key(KeyCode::Char(c), KeyModifiers::NONE));
        }
        app.chat_key(KeyCode::Char('j'), KeyModifiers::CONTROL);
        for c in "écho".chars() {
            app.chat_key(KeyCode::Char(c), KeyModifiers::NONE);
        }
        app.chat_key(KeyCode::Left, KeyModifiers::NONE);
        app.chat_key(KeyCode::Backspace, KeyModifiers::NONE);
        assert_eq!(app.chat.input, "first\néco");
        app.chat_key(KeyCode::Enter, KeyModifiers::NONE);
        match rx.try_recv().unwrap() {
            net::Command::ChatSend(body) => {
                assert_eq!(body["text"], "first\néco");
                assert_eq!(body["chat_id"], "test-id");
            }
            _ => panic!("expected chat request"),
        }
        assert!(app.chat.pending);
        app.chat_key(KeyCode::Char('x'), KeyModifiers::CONTROL);
        assert!(matches!(rx.try_recv().unwrap(), net::Command::ChatCancel(id) if id == "test-id"));
        app.chat_key(KeyCode::Esc, KeyModifiers::NONE);
        assert!(!app.chat.editing);
        assert_eq!(app.windows.len(), 1);
        app.chat_key(KeyCode::Enter, KeyModifiers::NONE);
        assert!(app.chat.editing);
    }
}
