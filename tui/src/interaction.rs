//! Pure table presentation and pointer arithmetic, shared by painting and selection.
use crate::window::Bounds;
use serde_json::Value;

pub fn rows<'a>(view: &str, data: &'a Value, filter: &str, sort: u8) -> Vec<&'a Value> {
    let field = if view == "COMP" { "series" } else { "data" };
    let mut rows: Vec<_> = data[field]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|r| {
            if view == "AL" {
                filter.is_empty() || r.to_string().contains(filter)
            } else if ["Market table", "Movers screener"].contains(&view) {
                r["name"]
                    .as_str()
                    .unwrap_or("")
                    .to_lowercase()
                    .contains(&filter.to_lowercase())
            } else {
                true
            } // Other panels are filtered and sorted by the server.
        })
        .collect();
    if view == "Market table" {
        let key = match sort {
            1 => "margin_gp",
            2 => "buy_price",
            _ => "",
        };
        if !key.is_empty() {
            rows.sort_by(|a, b| b[key].as_i64().cmp(&a[key].as_i64()));
        }
    }
    rows
}

/// Header/footer counts exclude the window border. Offset indexes the displayed row list.
pub fn row_at(
    rect: Bounds,
    x: u16,
    y: u16,
    headers: u16,
    footers: u16,
    offset: usize,
    count: usize,
) -> Option<usize> {
    if !rect.contains(x, y) || x <= rect.x || x >= rect.x.saturating_add(rect.w).saturating_sub(1) {
        return None;
    }
    let first = rect.y.saturating_add(1).saturating_add(headers);
    let end = rect
        .y
        .saturating_add(rect.h)
        .saturating_sub(1)
        .saturating_sub(footers);
    if y < first || y >= end {
        return None;
    }
    let index = offset.checked_add((y - first) as usize)?;
    (index < count).then_some(index)
}

pub fn item_id(row: &Value) -> Option<u64> {
    row["item_id"]
        .as_u64()
        .or_else(|| row["name"].as_str()?.parse().ok())
}
pub fn tile_bounds(inner: Bounds, cell: &Value) -> Option<Bounds> {
    let x = inner.x + (cell["x"].as_u64()? as u16).min(inner.w);
    let y = inner.y + 1 + (cell["y"].as_u64()? as u16).min(inner.h.saturating_sub(2));
    Some(Bounds {
        x,
        y,
        w: (cell["width"].as_u64()? as u16).min((inner.x + inner.w).saturating_sub(x)),
        h: (cell["height"].as_u64()? as u16).min((inner.y + inner.h).saturating_sub(y + 1)),
    })
}

#[derive(Clone, Copy)]
pub struct Press {
    pub x: u16,
    pub y: u16,
    pub moved: bool,
}
impl Press {
    pub fn motion(&mut self, x: u16, y: u16) {
        self.moved |= self.x.abs_diff(x).max(self.y.abs_diff(y)) >= 2;
    }
    pub fn released(self, x: u16, y: u16) -> bool {
        !self.moved && self.x.abs_diff(x).max(self.y.abs_diff(y)) < 2
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const R: Bounds = Bounds {
        x: 10,
        y: 5,
        w: 50,
        h: 20,
    };
    #[test]
    fn header_border_and_empty_area() {
        for y in 5..8 {
            assert_eq!(row_at(R, 20, y, 2, 0, 0, 3), None);
        }
        assert_eq!(row_at(R, 10, 8, 2, 0, 0, 3), None);
        assert_eq!(row_at(R, 20, 11, 2, 0, 0, 3), None);
        assert_eq!(row_at(R, 20, 24, 2, 0, 0, 30), None);
    }
    #[test]
    fn filtered_scrolled_and_sorted_rows_use_the_painted_order() {
        let data = serde_json::json!({"data":[
            {"item_id":1,"name":"Axe","buy_price":10},
            {"item_id":2,"name":"Log","buy_price":50},
            {"item_id":3,"name":"Oak log","buy_price":20},
            {"item_id":4,"name":"Yew log","buy_price":40}]});
        let filtered = rows("Market table", &data, "log", 0);
        assert_eq!(
            filtered[row_at(R, 20, 8, 2, 0, 0, filtered.len()).unwrap()]["item_id"],
            2
        );
        assert_eq!(
            filtered[row_at(R, 20, 8, 2, 0, 1, filtered.len()).unwrap()]["item_id"],
            3
        );
        let sorted = rows("Market table", &data, "log", 2);
        assert_eq!(
            sorted[row_at(R, 20, 9, 2, 0, 0, sorted.len()).unwrap()]["item_id"],
            4
        );
        let movers = rows("Movers screener", &data, "log", 0);
        assert_eq!(
            movers[row_at(R, 20, 8, 2, 0, 2, movers.len()).unwrap()]["item_id"],
            4
        );
    }
    #[test]
    fn press_drag_release_never_selects_even_after_returning() {
        let mut p = Press {
            x: 20,
            y: 10,
            moved: false,
        };
        assert!(p.released(20, 10));
        p.motion(22, 10);
        p.motion(20, 10);
        assert!(!p.released(20, 10));
        assert!(
            !Press {
                x: 20,
                y: 10,
                moved: false
            }
            .released(20, 12)
        );
    }
}

#[cfg(test)]
mod app_tests {
    use crate::*;
    fn make_app(view: &str) -> App {
        let (tx, _) = mpsc::unbounded_channel();
        let mut app = App::new("test-click".into(), Some(view.into()), tx);
        app.clamp(160, 50);
        app.windows[0].rect = Bounds {
            x: 0,
            y: 0,
            w: 100,
            h: 30,
        };
        let rows = serde_json::json!({"data":[{"item_id":1,"name":"Log"},{"item_id":2,"name":"Oak log"},{"item_id":3,"name":"Yew log"}]});
        app.data.insert("prices/movers".into(), rows.clone());
        app.data.insert("prices/latest".into(), rows.clone());
        app.data.insert("terminal:1".into(), rows);
        app
    }
    fn pointer(app: &mut App, kind: MouseEventKind, x: u16, y: u16) {
        app.mouse(event::MouseEvent {
            kind,
            column: x,
            row: y,
            modifiers: KeyModifiers::NONE,
        });
    }
    fn click(app: &mut App, x: u16, y: u16) {
        pointer(app, MouseEventKind::Down(MouseButton::Left), x, y);
        pointer(app, MouseEventKind::Up(MouseButton::Left), x, y);
    }
    #[test]
    fn every_item_table_maps_exact_painted_rows() {
        for view in [
            "Market table",
            "Movers screener",
            "TAS",
            "QM",
            "HCP",
            "MOST",
            "EQS",
            "AL",
        ] {
            let mut app = make_app(view);
            app.windows[0].scroll = 1;
            let y = if ["Market table", "Movers screener"].contains(&view) {
                3
            } else {
                4
            };
            assert_eq!(app.row_item(&app.windows[0], 20, y), Some((1, 2)), "{view}");
            assert_eq!(
                app.row_item(&app.windows[0], 20, y - 1),
                None,
                "{view} header"
            );
            assert_eq!(
                app.row_item(&app.windows[0], 20, y + 2),
                None,
                "{view} empty"
            );
        }
        let mut app = make_app("COMP");
        app.data.insert(
            "terminal:1".into(),
            serde_json::json!({"series":[{"name":"4151","points":[[0,100]]}]}),
        );
        assert_eq!(app.row_item(&app.windows[0], 20, 4), Some((0, 4151)));
        let mut app = make_app("HMAP");
        app.data.insert("terminal:1".into(),serde_json::json!({"cells":[{"x":0,"y":0,"width":20,"height":10,"item":{"item_id":42}}]}));
        assert_eq!(app.row_item(&app.windows[0], 4, 4), Some((0, 42)));
        assert_eq!(app.row_item(&app.windows[0], 1, 2), None);
    }
    #[test]
    fn single_click_retargets_without_duplicates_and_double_preserves_existing() {
        let mut app = make_app("Movers screener");
        let mut chart = app.windows[0].clone();
        chart.id = 2;
        chart.view = "Candlestick chart".into();
        chart.item = 99;
        chart.rect = Bounds {
            x: 101,
            y: 0,
            w: 59,
            h: 30,
        };
        app.windows.insert(0, chart);
        click(&mut app, 20, 3);
        let pending = app.pending_click.take().unwrap();
        app.chart_click(pending.selection, false);
        assert_eq!(app.windows.iter().find(|w| w.id == 2).unwrap().item, 1);
        assert_eq!(app.windows.len(), 2);
        click(&mut app, 20, 4);
        click(&mut app, 20, 4);
        assert_eq!(app.windows.len(), 3);
        assert_eq!(app.windows.iter().find(|w| w.id == 2).unwrap().item, 1);
        assert_eq!(app.windows.last().unwrap().item, 2);
    }
    #[test]
    fn drag_and_border_presses_do_not_select() {
        let mut app = make_app("Movers screener");
        pointer(&mut app, MouseEventKind::Down(MouseButton::Left), 20, 3);
        pointer(&mut app, MouseEventKind::Drag(MouseButton::Left), 23, 4);
        pointer(&mut app, MouseEventKind::Up(MouseButton::Left), 20, 3);
        assert!(app.pending_click.is_none());
        for (x, y) in [(20, 0), (0, 3), (99, 29)] {
            click(&mut app, x, y);
            assert!(app.pending_click.is_none());
        }
    }
}

#[cfg(test)]
mod link_click_tests {
    use crate::*;
    #[test]
    fn linked_chart_selection_and_comparison_cap() {
        let (tx, _) = mpsc::unbounded_channel();
        let mut app = App::new("test-link-click".into(), Some("QM".into()), tx);
        app.clamp(160, 50);
        let mut source = app.windows[0].clone();
        source.link = "red".into();
        let mut chart = source.clone();
        chart.id = 2;
        chart.view = "Candlestick chart".into();
        let mut other = chart.clone();
        other.id = 3;
        other.link = "blue".into();
        other.item = 99;
        let mut comp = source.clone();
        comp.id = 4;
        comp.view = "COMP".into();
        comp.set("ids", serde_json::json!([1, 2, 3, 4]));
        app.windows = vec![other, chart, comp, source];
        app.next_id = 5;
        let selection = |shift| RowPress {
            press: interaction::Press {
                x: 20,
                y: 5,
                moved: false,
            },
            window: 1,
            row: 0,
            item: 42,
            shift,
        };
        app.chart_click(selection(false), false);
        assert_eq!(app.windows.len(), 4);
        assert!(
            app.windows
                .iter()
                .filter(|w| w.link == "red")
                .all(|w| w.item == 42)
        );
        assert_eq!(app.windows.iter().find(|w| w.id == 3).unwrap().item, 99);
        let mut append = selection(true);
        append.item = 77;
        app.chart_click(append, false);
        let mut overflow = selection(true);
        overflow.item = 88;
        app.chart_click(overflow, false);
        let comp = app.windows.iter().find(|w| w.id == 4).unwrap();
        let ids = comp.options["ids"].as_array().unwrap();
        assert_eq!(ids.len(), 5);
        assert!(ids.iter().any(|v| v == 42) && ids.iter().any(|v| v == 77));
        assert!(!ids.iter().any(|v| v == 88));
    }
}
