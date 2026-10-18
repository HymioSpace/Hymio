#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod browser_login;

use std::time::Duration;

#[tauri::command]
async fn biz_get(
    base: String,
    path: String,
    credential: String,
    user_id: Option<String>,
) -> Result<serde_json::Value, String> {
    let url = reqwest::Url::parse(&format!("{}{}", base.trim_end_matches('/'), path))
        .map_err(|_| "无效的 Biz 地址")?;
    if !matches!(url.scheme(), "http" | "https")
        || !url.username().is_empty()
        || url.password().is_some()
        || !matches!(
            url.path().strip_prefix("/oath-biz").unwrap_or(url.path()),
            "/heartbeat" | "/list_traces" | "/query_trace"
        )
    {
        return Err("仅允许 Biz 健康与 Trace 查询".into());
    }
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .redirect(reqwest::redirect::Policy::none())
        .build()
        .map_err(|_| "HTTP 客户端初始化失败")?;
    let response = client
        .get(url)
        .bearer_auth(credential)
        .header("X-Oath-User-Id", user_id.unwrap_or_default())
        .send()
        .await
        .map_err(|_| "Biz 服务不可达")?;
    if !response.status().is_success() {
        return Err(format!("Biz HTTP {}", response.status()));
    }
    let bytes = response.bytes().await.map_err(|_| "响应读取失败")?;
    if bytes.len() > 16 * 1024 * 1024 {
        return Err("Trace 响应超过 16 MB".into());
    }
    serde_json::from_slice(&bytes).map_err(|_| "Biz 返回了无效 JSON".into())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            biz_get,
            browser_login::login_with_browser,
            browser_login::cancel_login
        ])
        .run(tauri::generate_context!())
        .expect("Hymio could not start");
}
