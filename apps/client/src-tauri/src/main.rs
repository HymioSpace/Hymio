#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::{fs, time::Duration};

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct LocalProfile {
    ws_url: String,
    biz_url: String,
    credential: String,
}

#[tauri::command]
fn local_oath_profile() -> Result<LocalProfile, String> {
    let home = std::env::var_os("HOME")
        .map(std::path::PathBuf::from)
        .ok_or("无法定位用户目录")?;
    let text = fs::read_to_string(home.join(".oath/oath.toml"))
        .map_err(|_| "未找到 ~/.oath/oath.toml，请先安装 Oath")?;
    let value: toml::Value = text.parse().map_err(|_| "Oath 配置格式无效")?;
    let services = value.get("services").ok_or("缺少 services 配置")?;
    let users = services
        .get("users")
        .and_then(|v| v.as_table())
        .ok_or("缺少用户凭据")?;
    let credential = users
        .iter()
        .find(|(_, v)| v.as_str() == Some("local"))
        .or_else(|| users.iter().next())
        .map(|(key, _)| key.clone())
        .ok_or("没有可用的用户凭据")?;
    let port = |key: &str, default: i64| {
        services
            .get(key)
            .and_then(|v| v.as_integer())
            .unwrap_or(default)
    };
    Ok(LocalProfile {
        ws_url: format!("ws://127.0.0.1:{}", port("gateway_port", 8765)),
        biz_url: format!("http://127.0.0.1:{}", port("biz_port", 8766)),
        credential,
    })
}

#[tauri::command]
async fn biz_get(
    base: String,
    path: String,
    credential: String,
) -> Result<serde_json::Value, String> {
    let url = reqwest::Url::parse(&format!("{}{}", base.trim_end_matches('/'), path))
        .map_err(|_| "无效的 Biz 地址")?;
    if !matches!(url.scheme(), "http" | "https")
        || !url.username().is_empty()
        || url.password().is_some()
        || !matches!(url.path(), "/heartbeat" | "/list_traces" | "/query_trace")
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
        .invoke_handler(tauri::generate_handler![local_oath_profile, biz_get])
        .run(tauri::generate_context!())
        .expect("Hymio could not start");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    #[ignore = "requires a local Oath deployment and ~/.oath/oath.toml"]
    fn native_biz_roundtrip() {
        let profile = local_oath_profile().expect("local user profile");
        tauri::async_runtime::block_on(async {
            let health = biz_get(
                profile.biz_url.clone(),
                "/heartbeat".into(),
                profile.credential.clone(),
            )
            .await
            .expect("native HTTP health");
            assert_eq!(health["status"], "alive");
            let traces = biz_get(
                profile.biz_url.clone(),
                "/list_traces?limit=1".into(),
                profile.credential.clone(),
            )
            .await
            .expect("authenticated native Trace query");
            assert!(traces["trace_ids"].is_array());
            if let Some(id) = traces["trace_ids"][0]["trace_id"].as_str() {
                let trace = biz_get(
                    profile.biz_url,
                    format!("/query_trace?trace_id={id}"),
                    profile.credential,
                )
                .await
                .expect("native Trace detail");
                assert!(trace["spans"].is_array());
            }
        });
    }
}
