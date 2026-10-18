use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
static LOGIN_GENERATION: AtomicU64 = AtomicU64::new(0);

#[tauri::command]
pub fn cancel_login() {
    LOGIN_GENERATION.fetch_add(1, Ordering::SeqCst);
}

fn open_login_url(url: &str) -> Result<(), String> {
    let parsed = reqwest::Url::parse(url).map_err(|_| "无效的登录地址")?;
    let local = matches!(parsed.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"));
    if !parsed.username().is_empty()
        || parsed.password().is_some()
        || !(parsed.scheme() == "https" || (parsed.scheme() == "http" && local))
    {
        return Err("登录地址需要 HTTPS，本机开发可使用 HTTP".into());
    }
    #[cfg(target_os = "macos")]
    let command = "open";
    #[cfg(target_os = "windows")]
    let command = "explorer";
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let command = "xdg-open";
    std::process::Command::new(command)
        .arg(url)
        .spawn()
        .map_err(|_| "无法打开系统浏览器")?;
    Ok(())
}

#[tauri::command]
pub async fn login_with_browser(backend: String) -> Result<serde_json::Value, String> {
    let generation = LOGIN_GENERATION.fetch_add(1, Ordering::SeqCst) + 1;
    use std::io::{BufRead, BufReader, Read, Write};
    use std::net::TcpListener;
    let base = reqwest::Url::parse(&backend).map_err(|_| "无效的 Hymio 地址")?;
    if !matches!(base.scheme(), "http" | "https")
        || !base.username().is_empty()
        || base.password().is_some()
    {
        return Err("无效的 Hymio 地址".into());
    }
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|_| "无法启动本机登录回调")?;
    listener
        .set_nonblocking(true)
        .map_err(|_| "无法启动本机登录回调")?;
    let port = listener
        .local_addr()
        .map_err(|_| "无法读取本机端口")?
        .port();
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "HTTP 初始化失败")?;
    let flow: serde_json::Value = client
        .post(format!("{}/auth/start", backend.trim_end_matches('/')))
        .json(&serde_json::json!({"return_uri": format!("http://127.0.0.1:{port}/hymio-callback")}))
        .send()
        .await
        .map_err(|_| "登录服务不可达")?
        .error_for_status()
        .map_err(|_| "登录服务拒绝请求")?
        .json()
        .await
        .map_err(|_| "无效的登录响应")?;
    let url = flow["authorization_url"].as_str().ok_or("缺少授权地址")?;
    if LOGIN_GENERATION.load(Ordering::SeqCst) != generation {
        return Err("登录已取消".into());
    }
    open_login_url(url)?;
    let grant = tauri::async_runtime::spawn_blocking(move || -> Result<String, String> {
        let deadline = std::time::Instant::now() + Duration::from_secs(300);
        while std::time::Instant::now() < deadline {
            if LOGIN_GENERATION.load(Ordering::SeqCst) != generation { return Err("登录已取消".into()); }
            match listener.accept() {
                Ok((mut stream, _)) => {
                    stream.set_read_timeout(Some(Duration::from_secs(3))).map_err(|_| "回调读取失败")?;
                    stream.set_write_timeout(Some(Duration::from_secs(3))).map_err(|_| "回调写入失败")?;
                    let mut request = String::new();
                    BufReader::new((&mut stream).take(8192)).read_line(&mut request).map_err(|_| "回调读取失败")?;
                    if !request.ends_with('\n') || request.split_whitespace().next() != Some("GET") { continue; }
                    let path = request.split_whitespace().nth(1).unwrap_or("");
                    let parsed = reqwest::Url::parse(&format!("http://127.0.0.1{path}")).map_err(|_| "无效回调")?;
                    if parsed.path() != "/hymio-callback" { continue; }
                    if parsed.query_pairs().any(|(key, _)| key == "error") { return Err("登录未完成，请重试".into()); }
                    let code = parsed.query_pairs().find(|(key, _)| key == "login_code").map(|(_, value)| value.to_string()).ok_or("缺少登录确认码")?;
                    let body = "Logged in. You can return to Hymio.";
                    let _ = write!(stream, "HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", body.len(), body);
                    return Ok(code);
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => std::thread::sleep(Duration::from_millis(50)),
                Err(_) => return Err("本机登录回调失败".into()),
            }
        }
        Err("登录等待已过期".into())
    }).await.map_err(|_| "登录回调中断")??;
    client
        .post(format!("{}/auth/exchange", backend.trim_end_matches('/')))
        .json(&serde_json::json!({"flow_id": flow["flow_id"], "login_code": grant}))
        .send()
        .await
        .map_err(|_| "登录服务不可达")?
        .error_for_status()
        .map_err(|_| "登录确认已失效")?
        .json()
        .await
        .map_err(|_| "无效的登录响应".into())
}
