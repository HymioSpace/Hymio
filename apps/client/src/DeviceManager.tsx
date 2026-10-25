import { useEffect, useState } from 'react';
import { Monitor, Globe, Smartphone, LoaderCircle } from 'lucide-react';
import type { LoginState } from './useLogin';
import { deviceImage, deviceRequest, type Device } from './deviceApi';
import { DeviceDetails } from './DeviceDetails';
import { DesktopSnapshot } from './DesktopSnapshot';
import { LinkPairing } from './LinkPairing';

export function DeviceManager({ login }: { login: LoginState }) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [screen, setScreen] = useState('');
  const [expanded, setExpanded] = useState('');
  const [zoomed, setZoomed] = useState(false);
  useEffect(
    () => () => {
      if (screen) URL.revokeObjectURL(screen);
    },
    [screen],
  );
  const cloudId = devices.find((device) => device.kind === 'cloud_desktop')?.device_id;
  useEffect(() => {
    setScreen('');
    setZoomed(false);
  }, [cloudId]);
  const load = () =>
    deviceRequest(login).then((result) => {
      setDevices(result.devices);
      setLoadError('');
    });
  useEffect(() => {
    let active = true;
    const refresh = () =>
      deviceRequest(login)
        .then((result) => {
          if (active) {
            setDevices(result.devices);
            setLoadError('');
          }
        })
        .catch(() => {
          if (active) setLoadError('暂时无法读取设备，稍后将自动重试。');
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [login.session?.access_token]);
  useEffect(() => {
    let active = true;
    void deviceRequest(login, '/ensure', {})
      .then(() => deviceRequest(login))
      .then((result) => {
        if (active) setDevices(result.devices);
      })
      .catch(() => {
        if (active) setError('暂时无法自动准备云电脑，需要使用时会自动重试');
      });
    return () => {
      active = false;
    };
  }, [login.session?.user_id, login.backend]);
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
  async function ensureDevice() {
    setBusy(true);
    setError('');
    try {
      const binding = await deviceRequest(login, '/ensure', {});
      if (binding.device?.device_id) setExpanded(binding.device.device_id);
      if (binding.action === 'unavailable')
        setError(
          binding.error === 'resource_access_denied'
            ? '云电脑尚未开通，请联系管理员。'
            : binding.error === 'resource_capacity_exhausted'
              ? '云电脑名额已满，请联系管理员。'
              : '云服务暂时无法连接，原环境会保留，稍后自动重试。',
        );
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      await load().catch(() => setError('暂时无法读取设备，请稍后刷新'));
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
      <LinkPairing login={login} />
      {loading && (
        <div className="device-loading" role="status">
          <LoaderCircle size={18} className="spin" />
          正在读取设备…
        </div>
      )}
      {loadError && (
        <p className="form-error" role="status">
          {loadError}
        </p>
      )}
      {devices.map((device) => (
        <div className="device-row" key={device.device_id}>
          <span className="device-symbol">
            {['ios', 'personal_android'].includes(device.kind) ? (
              <Smartphone size={20} />
            ) : device.kind === 'web' ? (
              <Globe size={20} />
            ) : (
              <Monitor size={20} />
            )}
          </span>
          <div className="device-info">
            <strong>{device.kind === 'cloud_desktop' ? '云电脑' : device.name}</strong>
            <small>
              {(
                {
                  online: '在线',
                  offline: '暂时无法连接',
                  missing: '等待自动更换',
                  preparing: '正在自动准备',
                  paused: '已暂停',
                  changing: '切换中',
                  recovery_required: '需要恢复',
                } as Record<string, string>
              )[device.state] || device.state}{' '}
              ·{' '}
              {device.provider === 'link'
                ? device.capabilities
                    .map(
                      (capability) =>
                        (
                          ({
                            bash: '终端',
                            computer: device.kind === 'personal_android' ? '手机操作' : '桌面',
                          }) as Record<string, string>
                        )[capability] || capability,
                    )
                    .join(' · ') ||
                  (device.kind === 'personal_android' &&
                  (device.permissions?.unlocked === false ||
                    device.permissions?.screen_awake === false)
                    ? '请在手机唤醒并解锁'
                    : device.permissions?.screen_recording === false
                      ? device.kind === 'personal_android'
                        ? '请在手机开启屏幕共享'
                        : '请在 Mac 允许屏幕录制'
                      : device.permissions?.accessibility === false
                        ? device.kind === 'personal_android'
                          ? '请在手机开启无障碍服务'
                          : '请在 Mac 允许辅助功能'
                        : device.kind === 'personal_android'
                          ? '等待手机权限上报'
                          : '等待权限上报；Shell 默认关闭')
                : device.capabilities.length
                  ? '终端 · 浏览器 · 桌面'
                  : '对话与消息同步'}
            </small>
          </div>
          {device.kind === 'cloud_desktop' && device.state === 'paused' && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() => void action(`/${device.device_id}/resume`)}
            >
              继续
            </button>
          )}
          {device.state === 'missing' && (
            <button className="text-button" disabled={busy} onClick={() => void ensureDevice()}>
              重试连接
            </button>
          )}
          {device.capabilities.includes('computer') && device.state !== 'missing' && (
            <button
              className="text-button"
              disabled={busy || !device.online}
              onClick={() => void preview(device.device_id)}
            >
              查看
            </button>
          )}
          {(device.capabilities.length > 0 || device.provider === 'link') && (
            <button
              className="text-button"
              onClick={() => setExpanded(expanded === device.device_id ? '' : device.device_id)}
            >
              管理
            </button>
          )}
          {!device.capabilities.length && device.provider !== 'link' && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    `解除 ${device.name}？${device.capabilities.length ? (device.preserves_files_on_revoke ? '仅解除绑定，服务器和文件保留。' : '云电脑将销毁，请先备份文件。') : '此设备将停止心跳同步。'}`,
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
            onEnsure={() => void ensureDevice()}
          />
        ))}
      {!loading && !loadError && !devices.some((device) => device.kind === 'cloud_desktop') && (
        <p className="dialog-note">当前没有云电脑。需要使用时，请联系管理员开通；对话不受影响。</p>
      )}
      <p className="dialog-note">
        云电脑可执行命令、浏览网页和操作桌面。Mac 和 Android 经 HymioDevice 接入；iPhone
        聊天端本身不提供远程控制。
      </p>
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
