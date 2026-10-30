//! Rendering only: prices, candles and financial metrics arrive precomputed from HTTP/WS.
use super::*;
use ratatui::widgets::{
    Axis, Chart, Dataset, GraphType,
    canvas::{Canvas, Line as CanvasLine, Rectangle},
};

pub fn line(f: &mut Frame, area: Rect, points: &[(f64, f64)], title: &str) {
    if area.width < 12 || area.height < 4 {
        return;
    }
    if points.is_empty() {
        f.render_widget(
            Paragraph::new(format!("{title}: no metric observations yet")),
            area,
        );
        return;
    }
    let lo = points.iter().map(|p| p.1).fold(f64::INFINITY, f64::min);
    let hi = points.iter().map(|p| p.1).fold(f64::NEG_INFINITY, f64::max);
    let pad = ((hi - lo) * 0.1).max(1.);
    let xmax = points.last().unwrap().0.max(1.);
    let dataset = Dataset::default()
        .name(title)
        .marker(symbols::Marker::Braille)
        .graph_type(GraphType::Line)
        .style(Style::default().fg(ACCENT))
        .data(points);
    f.render_widget(
        Chart::new(vec![dataset])
            .block(Block::default().title(title))
            .x_axis(
                Axis::default()
                    .title("metric event")
                    .bounds([0., xmax])
                    .labels(["0".to_string(), format!("{xmax:.0}")]),
            )
            .y_axis(
                Axis::default()
                    .bounds([lo - pad, hi + pad])
                    .labels([format!("{lo:.2}"), format!("{hi:.2}")]),
            )
            .style(Style::default().bg(BG)),
        area,
    );
}

impl App {
    pub fn candles(&self, f: &mut Frame, area: Rect, w: &Window) {
        if area.width < 25 || area.height < 12 {
            f.render_widget(Paragraph::new("Enlarge chart to at least 25×12"), area);
            return;
        }
        let rows = self.rows("history");
        let actual = self.data.get("history");
        let title = format!(
            "Item {}  {} [1=5m 2=1h 3=1d]  {}",
            self.item,
            self.tf,
            self.freshness("history")
        );
        f.render_widget(
            Paragraph::new(title),
            Rect::new(area.x, area.y, area.width, 1),
        );
        if actual.is_none_or(|v| v["item_id"].as_u64() != Some(self.item) || v["tf"] != self.tf) {
            f.render_widget(
                Paragraph::new("Loading selected series…"),
                Rect::new(area.x, area.y + 2, area.width, 1),
            );
            return;
        }
        let end = rows.len().saturating_sub(w.scroll);
        let start = end.saturating_sub(80);
        let rows = &rows[start..end];
        if rows.is_empty() {
            f.render_widget(
                Paragraph::new("No buckets available"),
                Rect::new(area.x, area.y + 2, area.width, 1),
            );
            return;
        }
        let lo = rows
            .iter()
            .filter_map(|r| r["low"].as_f64())
            .fold(f64::INFINITY, f64::min);
        let hi = rows
            .iter()
            .filter_map(|r| r["high"].as_f64())
            .fold(f64::NEG_INFINITY, f64::max);
        let pad = ((hi - lo) * 0.05).max(1.);
        let (ylo, yhi) = (lo - pad, hi + pad);
        let plot = Rect::new(
            area.x + 12,
            area.y + 3,
            area.width - 13,
            area.height.saturating_sub(12),
        );
        let vol = Rect::new(plot.x, plot.bottom() + 1, plot.width, 4);
        let count = rows.len();
        let max_x = count as f64;
        let hovered = self.hover.and_then(|(x, y)| {
            if plot.contains(Position::new(x, y)) {
                Some(window::chart_index(x, plot.x, plot.width, count))
            } else {
                None
            }
        });
        for i in 0..=4 {
            let y = plot.y + ((plot.height.saturating_sub(1)) as u32 * i / 4) as u16;
            let price = yhi - (yhi - ylo) * i as f64 / 4.;
            f.render_widget(
                Paragraph::new(format!("{price:>10.1}")).style(Style::default().fg(Color::Gray)),
                Rect::new(area.x, y, 11, 1),
            );
        }
        let canvas = Canvas::default()
            .background_color(BG)
            .marker(symbols::Marker::Braille)
            .x_bounds([-0.5, max_x - 0.5])
            .y_bounds([ylo, yhi])
            .paint(|ctx| {
                for i in 0..=4 {
                    let y = ylo + (yhi - ylo) * i as f64 / 4.;
                    ctx.draw(&CanvasLine {
                        x1: -0.5,
                        y1: y,
                        x2: max_x - 0.5,
                        y2: y,
                        color: Color::Rgb(34, 48, 62),
                    });
                }
                for i in 0..=8 {
                    let x = -0.5 + max_x * i as f64 / 8.;
                    ctx.draw(&CanvasLine {
                        x1: x,
                        y1: ylo,
                        x2: x,
                        y2: yhi,
                        color: Color::Rgb(24, 34, 46),
                    });
                }
                for (i, r) in rows.iter().enumerate() {
                    let (o, h, l, c) = (
                        num(&r["open"]),
                        num(&r["high"]),
                        num(&r["low"]),
                        num(&r["close"]),
                    );
                    let color = if c >= o { Color::Green } else { Color::Red };
                    let x = i as f64;
                    ctx.draw(&CanvasLine {
                        x1: x,
                        y1: l,
                        x2: x,
                        y2: h,
                        color,
                    });
                    ctx.draw(&Rectangle {
                        x: x - 0.28,
                        y: o.min(c),
                        width: 0.56,
                        height: (c - o).abs().max((yhi - ylo) / 200.),
                        color,
                    });
                }
                if let Some(i) = hovered {
                    let r = rows[i];
                    let x = i as f64;
                    let y = num(&r["close"]);
                    ctx.draw(&CanvasLine {
                        x1: x,
                        y1: ylo,
                        x2: x,
                        y2: yhi,
                        color: Color::Yellow,
                    });
                    ctx.draw(&CanvasLine {
                        x1: -0.5,
                        y1: y,
                        x2: max_x - 0.5,
                        y2: y,
                        color: Color::Yellow,
                    });
                }
            });
        f.render_widget(canvas, plot);
        let max_volume = rows.iter().map(|r| num(&r["volume"])).fold(1., f64::max);
        f.render_widget(
            Paragraph::new("Volume").style(Style::default().fg(Color::Blue)),
            Rect::new(area.x, vol.y, 11, 1),
        );
        f.render_widget(
            Canvas::default()
                .background_color(BG)
                .marker(symbols::Marker::Braille)
                .x_bounds([-0.5, max_x - 0.5])
                .y_bounds([0., max_volume])
                .paint(|ctx| {
                    for (i, r) in rows.iter().enumerate() {
                        ctx.draw(&CanvasLine {
                            x1: i as f64,
                            y1: 0.,
                            x2: i as f64,
                            y2: num(&r["volume"]),
                            color: Color::LightBlue,
                        });
                    }
                }),
            vol,
        );
        let chosen = hovered.unwrap_or(count - 1);
        let r = rows[chosen];
        let time = |v: &Value| {
            chrono::DateTime::from_timestamp(v.as_i64().unwrap_or(0), 0)
                .map(|t| t.format("%m-%d %H:%M").to_string())
                .unwrap_or_default()
        };
        f.render_widget(
            Paragraph::new(format!(
                "{} UTC{}{} UTC",
                time(&rows[0]["timestamp"]),
                " ".repeat(plot.width.saturating_sub(34) as usize),
                time(&rows[count - 1]["timestamp"])
            ))
            .style(Style::default().fg(Color::Gray)),
            Rect::new(plot.x, vol.bottom(), plot.width, 1),
        );
        f.render_widget(
            Paragraph::new(format!(
                "{} UTC  O:{} H:{} L:{} C:{} V:{}",
                time(&r["timestamp"]),
                val(&r["open"]),
                val(&r["high"]),
                val(&r["low"]),
                val(&r["close"]),
                val(&r["volume"])
            ))
            .style(Style::default().fg(Color::Yellow)),
            Rect::new(area.x, area.y + 1, area.width, 1),
        );
        f.render_widget(Paragraph::new("Mean-envelope candles, not trade OHLC. Hover crosshair · wheel history · palette: item 4151").style(Style::default().fg(Color::Gray)),Rect::new(area.x,area.bottom()-1,area.width,1));
    }
    pub fn metric_points(&self) -> Vec<(f64, f64)> {
        self.job_events
            .get(&self.selected_job)
            .into_iter()
            .flatten()
            .filter(|e| e["type"] == "metric")
            .filter_map(|e| {
                e["data"]["values"][&self.metric]
                    .as_f64()
                    .or_else(|| e["data"][&self.metric].as_f64())
            })
            .filter(|v| v.is_finite())
            .enumerate()
            .map(|(i, v)| (i as f64, v))
            .collect()
    }
}
pub fn num(v: &Value) -> f64 {
    v.as_f64().unwrap_or(0.)
}
