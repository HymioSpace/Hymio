import { useEffect, useState } from 'react';
import { Monitor, Globe, Smartphone, LoaderCircle, Plus } from 'lucide-react';
import type { LoginState } from './useLogin';
import { deviceImage, deviceRequest, type Device } from './deviceApi';
import { DeviceDetails } from './DeviceDetails';
import { DesktopSnapshot } from './DesktopSnapshot';

export function DeviceManager({ login }: { login: LoginState }) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [screen, setScreen] = useState('');
  const [expanded, setExpanded] = useState('');
  const [zoomed, setZoomed] = useState(false);
  useEffect(
    () => () => {
      if (screen) URL.revokeObjectURL(screen);
    },
    [screen],
  );
  const load = () => deviceRequest(login).then((result) => setDevices(result.devices));
  useEffect(() => {
    let active = true;
    const refresh = () =>
      deviceRequest(login)
        .then((result) => {
          if (active) setDevices(result.devices);
        })
        .catch(() => {
          if (active) setError('暂时无法读取设备');
        });
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [login.session?.access_token]);
  async function action(path: string) {
    setBusy(true);
    setError('');
    try {
      const result = await deviceRequest(login, path, {});
      await load();
      if (result.stopped === false)
        setError('已解除绑定并阻止新命令，但云电脑未能停止，请联系部署者处理。');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  async function preview(deviceId: string) {
    setBusy(true);
    setError('');
    try {
      const result = await deviceRequest(login, '/execute', {
        device_id: deviceId,
        invocation_id: crypto.randomUUID(),
        capability: 'computer',
        arguments: { action: 'screenshot' },
        timeout: 10,
      });
      if (result.status !== 'succeeded') throw new Error('暂时无法读取桌面，请检查设备状态后重试');
      setScreen(URL.createObjectURL(await deviceImage(login, result.result.screenshot.url)));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="device-manager" aria-label="我的设备">
      <div className="device-heading">
        <h3>我的设备</h3>
        <span>一个 Hymio，随处继续</span>
      </div>
      {devices.map((device) => (
        <div className="device-row" key={device.device_id}>
          <span className="device-symbol">
            {device.kind === 'ios' ? (
              <Smartphone size={20} />
            ) : device.kind === 'web' ? (
              <Globe size={20} />
            ) : (
              <Monitor size={20} />
            )}
          </span>
          <div className="device-info">
            <strong>{device.name}</strong>
            <small>
              {(
                {
                  online: '在线',
                  offline: '离线',
                  paused: '已暂停',
                  changing: '切换中',
                  recovery_required: '需要恢复',
                } as Record<string, string>
              )[device.state] || device.state}{' '}
              · {device.capabilities.length ? '终端 · 浏览器 · 桌面' : '对话与消息同步'}
            </small>
            <code title={device.device_id}>{device.device_id.slice(0, 10)}</code>
          </div>
          {device.capabilities.includes('computer') && (
            <button
              className="text-button"
              disabled={busy || !device.online}
              onClick={() => void preview(device.device_id)}
            >
              查看
            </button>
          )}
          {device.capabilities.length > 0 && (
            <button
              className="text-button"
              onClick={() => setExpanded(expanded === device.device_id ? '' : device.device_id)}
            >
              管理
            </button>
          )}
          {!device.capabilities.length && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    `解除 ${device.name}？${device.capabilities.length ? (device.preserves_files_on_revoke ? '云电脑将停止运行，文件保留。' : '云电脑将销毁，请先备份文件。') : '此设备将停止心跳同步。'}`,
                  )
                )
                  void action(`/${device.device_id}/revoke`);
              }}
            >
              解除
            </button>
          )}
        </div>
      ))}
      {devices
        .filter((device) => device.device_id === expanded)
        .map((device) => (
          <DeviceDetails
            key={device.device_id}
            device={device}
            login={login}
            busy={busy}
            onAction={(path) => void action(path)}
          />
        ))}
      {!devices.some((device) => device.kind === 'cloud_desktop') && (
        <p className="dialog-note">
          还没有可执行设备。添加云电脑后，Hymio 才能浏览网页、执行命令和操作桌面。
        </p>
      )}
      {!devices.some((device) => device.kind === 'cloud_desktop') && (
        <button className="device-add" disabled={busy} onClick={() => void action('/provision')}>
          {busy ? <LoaderCircle className="spin" size={16} /> : <Plus size={16} />}添加云电脑
        </button>
      )}
      <p className="dialog-note">云电脑可执行命令、浏览网页和操作桌面。手机仅用于对话。</p>
      {screen && (
        <div className="device-preview">
          <button
            className="snapshot-image"
            onClick={() => setZoomed(true)}
            aria-label="放大桌面快照"
          >
            <img src={screen} alt="云电脑当前桌面截图" />
          </button>
          <button className="text-button" onClick={() => setScreen('')}>
            收起截图
          </button>
        </div>
      )}
      {screen && zoomed && <DesktopSnapshot src={screen} onClose={() => setZoomed(false)} />}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
    </section>
  );
}
