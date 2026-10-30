use serde_json::Value;
use std::time::Duration;
use tokio::sync::mpsc;

#[derive(Debug)]
pub enum Message {
    Data(String, Value),
    Error(String, String),
}

pub fn connect(server: String, tx: mpsc::UnboundedSender<Message>) {
    tokio::spawn(async move {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(16))
            .build()
            .expect("HTTP client");
        let mut backoff = 1;
        loop {
            let calls = ["health", "prices/latest", "alch/gaps"]
                .into_iter()
                .map(|route| {
                    let (client, tx, server) = (client.clone(), tx.clone(), server.clone());
                    async move {
                        let result = async {
                            client
                                .get(format!("{server}/api/{route}"))
                                .send()
                                .await?
                                .error_for_status()?
                                .json::<Value>()
                                .await
                        }
                        .await;
                        match result {
                            Ok(value) => {
                                let _ = tx.send(Message::Data(route.into(), value));
                                true
                            }
                            Err(error) => {
                                let _ = tx.send(Message::Error(route.into(), error.to_string()));
                                false
                            }
                        }
                    }
                });
            let results = futures_util::future::join_all(calls).await;
            if results.iter().all(|r| *r) {
                backoff = 1;
            } else {
                backoff = (backoff * 2).min(30);
            }
            if tx.is_closed() {
                break;
            }
            tokio::time::sleep(Duration::from_secs(if backoff == 1 { 5 } else { backoff })).await;
        }
    });
}
