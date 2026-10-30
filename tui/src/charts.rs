//! Rendering only: prices, candles and financial metrics arrive precomputed from HTTP/WS.
use super::*;
use ratatui::widgets::{Axis, Chart, Dataset, GraphType};

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
