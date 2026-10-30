use super::*;

impl App {
    pub fn jobs(&self, f: &mut Frame, area: Rect, w: &Window) {
        if area.height < 12 {
            f.render_widget(
                Paragraph::new("Enlarge Jobs to see list, metrics and logs"),
                area,
            );
            return;
        }
        let parts = Layout::vertical([
            Constraint::Length(1),
            Constraint::Length(7),
            Constraint::Length(9),
            Constraint::Min(3),
        ])
        .split(area);
        f.render_widget(Paragraph::new(format!("{} • stream: {} • j/k select • c cancel • wheel logs • dataset:{} track:{} horizon:{}h",self.freshness("jobs"),self.stream_state,self.dataset,self.track,self.horizon)),parts[0]);
        let all = self.rows("jobs");
        let selected = all
            .iter()
            .position(|r| r["id"] == self.selected_job)
            .unwrap_or(0);
        let start = selected.saturating_sub(4);
        let rows = all.into_iter().skip(start).map(|r| {
            let id = r["id"].as_str().unwrap_or("");
            let status = r["status"].as_str().unwrap_or("unknown");
            Row::new([
                format!(
                    "{} {}",
                    if id == self.selected_job { "▶" } else { " " },
                    &id[..id.len().min(8)]
                ),
                val(&r["kind"]),
                status.into(),
                format!("{:.0}%", r["progress"].as_f64().unwrap_or(0.) * 100.),
                val(&r["params"]["dataset"]),
                val(&r["error"]),
            ])
            .style(Style::default().fg(if id == self.selected_job {
                ACCENT
            } else if status == "failed" {
                Color::Red
            } else {
                FG
            }))
        });
        f.render_widget(
            Table::new(
                rows,
                [
                    Constraint::Length(12),
                    Constraint::Length(12),
                    Constraint::Length(12),
                    Constraint::Length(10),
                    Constraint::Length(16),
                    Constraint::Min(10),
                ],
            )
            .header(
                Row::new(["Job ID", "Kind", "Status", "Progress", "Dataset", "Error"])
                    .style(Style::default().fg(ACCENT)),
            ),
            parts[1],
        );
        charts::line(
            f,
            parts[2],
            &self.metric_points(),
            &format!("{} · evaluation artifacts", self.metric),
        );
        self.log_tail(f, parts[3], w);
    }
    pub fn log_tail(&self, f: &mut Frame, area: Rect, w: &Window) {
        let events = self.job_events.get(&self.selected_job);
        let lines: Vec<Line> = events
            .into_iter()
            .flatten()
            .filter(|e| e["type"] == "log")
            .map(|e| {
                let channel = e["data"]["channel"].as_str().unwrap_or("log");
                Line::styled(
                    format!("[{channel}] {}", e["data"]["line"].as_str().unwrap_or("")),
                    Style::default().fg(if channel == "stderr" { Color::Red } else { FG }),
                )
            })
            .collect();
        let block = Block::default().borders(Borders::TOP).title(format!(
            " Live log • {} • {} lines • offset {} ",
            &self.selected_job[..self.selected_job.len().min(8)],
            lines.len(),
            w.scroll
        ));
        let inner = block.inner(area);
        f.render_widget(block, area);
        if lines.is_empty() {
            f.render_widget(Paragraph::new("No logs yet. / → Start benchmark, eval, train or backtest. Jobs run on the server after this window closes."),inner);
            return;
        }
        let end = lines.len().saturating_sub(w.scroll);
        let start = end.saturating_sub(inner.height as usize);
        f.render_widget(Paragraph::new(lines[start..end].to_vec()), inner);
    }
    pub fn movers(&self, f: &mut Frame, area: Rect, w: &Window) {
        if area.height < 2 {
            return;
        }
        f.render_widget(
            Paragraph::new(format!(
                "{} • exact 5m midpoint returns • ranked by absolute change",
                self.freshness("prices/movers")
            )),
            Rect::new(area.x, area.y, area.width, 1),
        );
        let rows = self
            .rows("prices/movers")
            .into_iter()
            .filter(|r| {
                val(&r["name"])
                    .to_lowercase()
                    .contains(&w.filter.to_lowercase())
            })
            .skip(w.scroll)
            .map(|r| {
                Row::new([
                    val(&r["item_id"]),
                    val(&r["name"]),
                    val(&r["price"]),
                    format!("{:+.2}%", charts::num(&r["change_pct"])),
                    val(&r["volume"]),
                ])
                .style(Style::default().fg(
                    if charts::num(&r["change_pct"]) >= 0. {
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
                    Constraint::Length(9),
                    Constraint::Min(24),
                    Constraint::Length(18),
                    Constraint::Length(16),
                    Constraint::Length(16),
                ],
            )
            .header(
                Row::new([
                    "Item ID",
                    "Name",
                    "Mean price",
                    "Change 5m",
                    "Min-side volume",
                ])
                .style(Style::default().fg(ACCENT)),
            ),
            Rect::new(area.x, area.y + 1, area.width, area.height - 1),
        );
    }
    pub fn models(&self, f: &mut Frame, area: Rect, w: &Window) {
        if area.height < 2 {
            return;
        }
        f.render_widget(
            Paragraph::new(format!(
                "{} • saved development results (holdout directories excluded)",
                self.freshness("models/runs")
            )),
            Rect::new(area.x, area.y, area.width, 1),
        );
        let mut lines = vec![];
        for run in self.rows("models/runs") {
            let path = run["path"].as_str().unwrap_or("");
            let label = path.split("/runs/").last().unwrap_or(path);
            if !label.to_lowercase().contains(&w.filter.to_lowercase()) {
                continue;
            }
            lines.push(Line::styled(
                format!("{label}  status:{}", val(&run["metadata"]["status"])),
                Style::default().fg(ACCENT),
            ));
            if let Some(metrics) = run["metrics"].as_array() {
                for m in metrics {
                    lines.push(Line::from(format!(
                        "  {}  net_gp:{}  gp/hr:{}  drawdown:{}  fill:{}",
                        val(&m["path"]),
                        val(&m["values"]["net_gp"]),
                        val(&m["values"]["net_gp_per_hour"]),
                        val(&m["values"]["max_drawdown"]),
                        val(&m["values"]["fill_rate"])
                    )));
                }
            }
        }
        f.render_widget(
            Paragraph::new(lines.into_iter().skip(w.scroll).collect::<Vec<_>>()),
            Rect::new(area.x, area.y + 1, area.width, area.height - 1),
        );
    }
    pub fn collector(&self, f: &mut Frame, area: Rect, w: &Window) {
        let mut lines = vec![
            Line::from(self.freshness("collector/health")),
            Line::from(""),
        ];
        if let Some(v) = self.data.get("collector/health") {
            lines.push(Line::styled(
                format!("Forward snapshots: {}", val(&v["snapshot_count"])),
                Style::default().fg(ACCENT),
            ));
            if let Some(buckets) = v["buckets"].as_array() {
                for b in buckets {
                    lines.push(Line::from(format!(
                        "{}s  oldest:{}  newest:{}  missing buckets:{}",
                        val(&b["resolution_seconds"]),
                        val(&b["oldest"]),
                        val(&b["newest"]),
                        val(&b["gaps"])
                    )));
                }
            }
            lines.push(Line::from(""));
            lines.push(Line::styled(
                "Ledger row counts",
                Style::default().fg(ACCENT),
            ));
            if let Some(ledgers) = v["ledger_rows"].as_object() {
                for (name, tables) in ledgers {
                    lines.push(Line::from(name.clone()));
                    if let Some(tables) = tables.as_object() {
                        for (name, count) in tables {
                            lines.push(Line::from(format!("  {name:<24} {count}")));
                        }
                    }
                }
            }
        }
        f.render_widget(
            Paragraph::new(lines.into_iter().skip(w.scroll).collect::<Vec<_>>()),
            area,
        );
    }
    pub fn console(&self, f: &mut Frame, area: Rect, w: &Window) {
        let end = self.errors.len().saturating_sub(w.scroll);
        let start = end.saturating_sub(area.height as usize);
        f.render_widget(
            Paragraph::new(
                self.errors[start..end]
                    .iter()
                    .map(|s| Line::from(s.clone()))
                    .collect::<Vec<_>>(),
            )
            .wrap(Wrap { trim: false }),
            area,
        );
    }
    pub fn research_table(&self, f: &mut Frame, area: Rect, w: &Window, battery: bool) {
        if area.height < 2 {
            return;
        }
        let key = if battery {
            "research/battery"
        } else {
            "research/participation"
        };
        f.render_widget(
            Paragraph::new(format!(
                "{} • persisted research artifacts",
                self.freshness(key)
            )),
            Rect::new(area.x, area.y, area.width, 1),
        );
        let rows = self
            .rows(key)
            .into_iter()
            .filter(|r| {
                r.to_string()
                    .to_lowercase()
                    .contains(&w.filter.to_lowercase())
            })
            .skip(w.scroll)
            .map(|r| {
                if battery {
                    Row::new([
                        val(&r["id"]),
                        val(&r["participation_bps"]),
                        val(&r["net_gp"]),
                        val(&r["p_raw"]),
                        val(&r["p_adjusted"]),
                        val(&r["verdict"]),
                    ])
                } else {
                    Row::new([
                        val(&r["model"]),
                        val(&r["preset"]),
                        val(&r["fold"]),
                        val(&r["first_profitable_bps"]),
                        val(&r["min_gp"]),
                        val(&r["max_gp"]),
                    ])
                }
            });
        let header = if battery {
            [
                "Rule",
                "Share bps",
                "Net GP",
                "Raw p",
                "Corrected p",
                "Verdict",
            ]
        } else {
            ["Model", "Preset", "Fold", "First + bps", "Min GP", "Max GP"]
        };
        f.render_widget(
            Table::new(
                rows,
                [
                    Constraint::Min(24),
                    Constraint::Length(14),
                    Constraint::Length(16),
                    Constraint::Length(16),
                    Constraint::Length(16),
                    Constraint::Length(18),
                ],
            )
            .header(Row::new(header).style(Style::default().fg(ACCENT))),
            Rect::new(area.x, area.y + 1, area.width, area.height - 1),
        );
    }
}
