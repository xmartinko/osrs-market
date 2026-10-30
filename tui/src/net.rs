use futures_util::StreamExt;
use serde_json::Value;
use std::time::Duration;
use tokio::sync::mpsc;

#[derive(Debug)]
pub enum Message {
    Data(String, Value),
    Error(String, String),
    Started(Value),
    Event(String, Value),
    Stream(String),
    ChatStarted(Value),
}
pub enum Command {
    Terminal(String, String, Value),
    DeleteAlert(u64),
    TerminalWindows(Vec<String>),
    Start(String, Value),
    Cancel(String),
    Watch(String),
    ChatSend(Value),
    ChatWatch(String),
    ChatCancel(String),
}
async fn fetch(
    client: &reqwest::Client,
    server: &str,
    route: &str,
) -> Result<Value, reqwest::Error> {
    client
        .get(format!("{server}/api/{route}"))
        .send()
        .await?
        .error_for_status()?
        .json()
        .await
}
async fn send_data(
    client: &reqwest::Client,
    server: &str,
    route: &str,
    key: &str,
    tx: &mpsc::UnboundedSender<Message>,
) -> bool {
    match fetch(client, server, route).await {
        Ok(value) => {
            let _ = tx.send(Message::Data(key.into(), value));
            true
        }
        Err(error) => {
            let _ = tx.send(Message::Error(key.into(), error.to_string()));
            false
        }
    }
}
pub fn connect(
    server: String,
    tx: mpsc::UnboundedSender<Message>,
) -> mpsc::UnboundedSender<Command> {
    let (commands, mut rx) = mpsc::unbounded_channel();
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(16))
        .build()
        .expect("HTTP client");
    let (poll_client, poll_server, poll_tx) = (client.clone(), server.clone(), tx.clone());
    tokio::spawn(async move {
        let mut backoff = 1;
        loop {
            let routes = [
                "health",
                "terminal/alerts",
                "usage",
                "chats",
                "prices/latest",
                "alch/gaps",
                "prices/movers",
                "jobs",
                "models/runs",
                "collector/health",
                "research/battery",
                "research/participation",
            ];
            let calls = routes
                .into_iter()
                .map(|route| send_data(&poll_client, &poll_server, route, route, &poll_tx));
            let results = futures_util::future::join_all(calls).await;
            if results[0] {
                backoff = 1;
            } else {
                backoff = (backoff * 2).min(30);
            }
            if poll_tx.is_closed() {
                break;
            }
            tokio::time::sleep(Duration::from_secs(if backoff == 1 { 3 } else { backoff })).await;
        }
    });
    tokio::spawn(async move {
        let mut terminal_tasks =
            std::collections::HashMap::<String, (Value, tokio::task::JoinHandle<()>)>::new();
        let mut watch = None::<tokio::task::JoinHandle<()>>;
        let mut chat_watch = None::<tokio::task::JoinHandle<()>>;
        while let Some(command) = rx.recv().await {
            match command {
                Command::TerminalWindows(keys) => {
                    terminal_tasks.retain(|key, (_, task)| {
                        let keep = keys.contains(key)
                            || key.starts_with("alert-create:") && !task.is_finished();
                        if !keep {
                            task.abort();
                        }
                        keep
                    });
                }
                Command::Terminal(key, route, body) => {
                    if terminal_tasks
                        .get(&key)
                        .is_some_and(|(old, _)| old == &body)
                    {
                        continue;
                    }
                    if let Some((_, task)) = terminal_tasks.remove(&key) {
                        task.abort();
                    }
                    let (client, server, tx) = (client.clone(), server.clone(), tx.clone());
                    let saved = body.clone();
                    let task_key = key.clone();
                    let task = tokio::spawn(async move {
                        loop {
                            let result = client
                                .post(format!("{server}/api/{route}"))
                                .json(&body)
                                .send()
                                .await;
                            match result {
                                Ok(r) => {
                                    let status = r.status();
                                    match r.json::<Value>().await {
                                        Ok(v) if status.is_success() => {
                                            let _ = tx.send(Message::Data(task_key.clone(), v));
                                        }
                                        Ok(v) => {
                                            let _ = tx.send(Message::Error(
                                                task_key.clone(),
                                                format!("{status}: {}", v["detail"]),
                                            ));
                                        }
                                        Err(e) => {
                                            let _ = tx.send(Message::Error(
                                                task_key.clone(),
                                                e.to_string(),
                                            ));
                                        }
                                    }
                                }
                                Err(e) => {
                                    let _ =
                                        tx.send(Message::Error(task_key.clone(), e.to_string()));
                                }
                            }
                            if tx.is_closed() || route == "terminal/alerts" {
                                break;
                            }
                            tokio::time::sleep(Duration::from_secs(10)).await;
                        }
                    });
                    terminal_tasks.insert(key, (saved, task));
                }
                Command::DeleteAlert(id) => {
                    let (client, server, tx) = (client.clone(), server.clone(), tx.clone());
                    tokio::spawn(async move {
                        if let Err(e) = client
                            .delete(format!("{server}/api/terminal/alerts/{id}"))
                            .send()
                            .await
                        {
                            let _ =
                                tx.send(Message::Error("terminal/alerts".into(), e.to_string()));
                        }
                        send_data(&client, &server, "terminal/alerts", "terminal/alerts", &tx)
                            .await;
                    });
                }

                Command::ChatSend(body) => {
                    let (client, server, tx) = (client.clone(), server.clone(), tx.clone());
                    tokio::spawn(async move {
                        let result = async {
                            let response = client
                                .post(format!("{server}/api/chat"))
                                .json(&body)
                                .send()
                                .await
                                .map_err(|e| e.to_string())?;
                            let status = response.status();
                            let value: Value = response.json().await.map_err(|e| e.to_string())?;
                            if !status.is_success() {
                                return Err(format!("{status}: {}", value["detail"]));
                            }
                            Ok(value)
                        }
                        .await;
                        match result {
                            Ok(value) => {
                                let _ = tx.send(Message::ChatStarted(value));
                            }
                            Err(error) => {
                                let _ = tx.send(Message::Error("chat send".into(), error));
                            }
                        }
                    });
                }
                Command::ChatCancel(id) => {
                    let (client, server, tx) = (client.clone(), server.clone(), tx.clone());
                    tokio::spawn(async move {
                        match client
                            .post(format!("{server}/api/chat/{id}/cancel"))
                            .send()
                            .await
                        {
                            Ok(r) if r.status().is_success() => {}
                            Ok(r) => {
                                let _ = tx.send(Message::Error(
                                    "chat cancel".into(),
                                    r.status().to_string(),
                                ));
                            }
                            Err(e) => {
                                let _ =
                                    tx.send(Message::Error("chat cancel".into(), e.to_string()));
                            }
                        }
                        send_data(&client, &server, &format!("chat/{id}"), "chat", &tx).await;
                    });
                }
                Command::ChatWatch(id) => {
                    if let Some(task) = chat_watch.take() {
                        task.abort();
                    }
                    if id.is_empty() {
                        continue;
                    }
                    let (client, server, tx) = (client.clone(), server.clone(), tx.clone());
                    chat_watch = Some(tokio::spawn(async move {
                        let mut after = 0i64;
                        let mut backoff = 1;
                        loop {
                            send_data(&client, &server, &format!("chat/{id}"), "chat", &tx).await;
                            let base = server
                                .replacen("https://", "wss://", 1)
                                .replacen("http://", "ws://", 1);
                            let url = format!("{base}/api/chat/{id}/stream?after={after}");
                            match tokio_tungstenite::connect_async(url).await {
                                Ok((mut socket, _)) => {
                                    backoff = 1;
                                    while let Some(message) = socket.next().await {
                                        match message {
                                            Ok(tokio_tungstenite::tungstenite::Message::Text(
                                                text,
                                            )) => {
                                                if let Ok(event) =
                                                    serde_json::from_str::<Value>(&text)
                                                {
                                                    after = event["seq"].as_i64().unwrap_or(after);
                                                    if event["type"] == "done"
                                                        || event["type"] == "thinking"
                                                    {
                                                        send_data(
                                                            &client,
                                                            &server,
                                                            &format!("chat/{id}"),
                                                            "chat",
                                                            &tx,
                                                        )
                                                        .await;
                                                    }
                                                    if event["type"] == "done" {
                                                        send_data(
                                                            &client, &server, "usage", "usage", &tx,
                                                        )
                                                        .await;
                                                    }
                                                    if event["type"] == "log" {
                                                        let _ = tx.send(Message::Data(
                                                            "chat_progress".into(),
                                                            event["data"].clone(),
                                                        ));
                                                    }
                                                }
                                            }
                                            Ok(tokio_tungstenite::tungstenite::Message::Close(
                                                _,
                                            )) => break,
                                            Err(_) => break,
                                            _ => {}
                                        }
                                    }
                                }
                                Err(e) => {
                                    let _ = tx
                                        .send(Message::Error("chat stream".into(), e.to_string()));
                                }
                            }
                            if tx.is_closed() {
                                break;
                            }
                            tokio::time::sleep(Duration::from_secs(backoff)).await;
                            backoff = (backoff * 2).min(30);
                        }
                    }));
                }
                Command::Start(kind, params) => {
                    let (client, server, tx) = (client.clone(), server.clone(), tx.clone());
                    tokio::spawn(async move {
                        let result = async {
                            client
                                .post(format!("{server}/api/jobs"))
                                .json(&serde_json::json!({"kind":kind,"params":params}))
                                .send()
                                .await?
                                .error_for_status()?
                                .json::<Value>()
                                .await
                        }
                        .await;
                        match result {
                            Ok(value) => {
                                let _ = tx.send(Message::Started(value));
                            }
                            Err(e) => {
                                let _ = tx.send(Message::Error("start job".into(), e.to_string()));
                            }
                        }
                        send_data(&client, &server, "jobs", "jobs", &tx).await;
                    });
                }
                Command::Cancel(id) => {
                    let (client, server, tx) = (client.clone(), server.clone(), tx.clone());
                    tokio::spawn(async move {
                        if let Err(e) = async {
                            client
                                .post(format!("{server}/api/jobs/{id}/cancel"))
                                .send()
                                .await?
                                .error_for_status()
                        }
                        .await
                        {
                            let _ = tx.send(Message::Error("cancel job".into(), e.to_string()));
                        }
                        send_data(&client, &server, "jobs", "jobs", &tx).await;
                    });
                }
                Command::Watch(id) => {
                    if let Some(task) = watch.take() {
                        task.abort();
                    }
                    let (client, server, tx) = (client.clone(), server.clone(), tx.clone());
                    watch = Some(tokio::spawn(async move {
                        let mut after = 0i64;
                        let mut backoff = 1;
                        loop {
                            send_data(
                                &client,
                                &server,
                                &format!("jobs/{id}"),
                                &format!("jobs/{id}"),
                                &tx,
                            )
                            .await;
                            let base = server
                                .replacen("https://", "wss://", 1)
                                .replacen("http://", "ws://", 1);
                            let url = format!("{base}/api/jobs/{id}/stream?after={after}");
                            let mut terminal = false;
                            match tokio_tungstenite::connect_async(url).await {
                                Ok((mut socket, _)) => {
                                    backoff = 1;
                                    let _ = tx.send(Message::Stream("attached".into()));
                                    while let Some(message) = socket.next().await {
                                        match message {
                                            Ok(tokio_tungstenite::tungstenite::Message::Text(
                                                text,
                                            )) => {
                                                if let Ok(event) =
                                                    serde_json::from_str::<Value>(&text)
                                                {
                                                    after = after
                                                        .max(event["seq"].as_i64().unwrap_or(0));
                                                    if event["type"] == "status" {
                                                        terminal = matches!(
                                                            event["data"]["status"].as_str(),
                                                            Some(
                                                                "succeeded"
                                                                    | "failed"
                                                                    | "cancelled"
                                                            )
                                                        );
                                                    }
                                                    let _ =
                                                        tx.send(Message::Event(id.clone(), event));
                                                }
                                            }
                                            Ok(tokio_tungstenite::tungstenite::Message::Close(
                                                _,
                                            ))
                                            | Err(_) => break,
                                            _ => {}
                                        }
                                    }
                                }
                                Err(e) => {
                                    let _ =
                                        tx.send(Message::Error("job stream".into(), e.to_string()));
                                }
                            }
                            if terminal {
                                let _ =
                                    tx.send(Message::Stream("complete / replay available".into()));
                                break;
                            }
                            let _ = tx.send(Message::Stream(format!(
                                "reconnecting in {backoff}s (cursor {after})"
                            )));
                            tokio::time::sleep(Duration::from_secs(backoff)).await;
                            backoff = (backoff * 2).min(30);
                            if tx.is_closed() {
                                break;
                            }
                        }
                    }));
                }
            }
        }
        for (_, (_, task)) in terminal_tasks {
            task.abort();
        }
        if let Some(task) = watch {
            task.abort();
        }
    });
    commands
}
