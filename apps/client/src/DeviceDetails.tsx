import { useEffect, useState } from 'react';
import type { LoginState } from './useLogin';
import { deviceRequest, type Device } from './deviceApi';

interface CommandRecord {
  invocation_id: string;
  status: string;
  request: { capability?: string };
  result: unknown;
  submitted_at: number;
}
export function DeviceDetails({
  device,
  login,
  busy,
  onAction,
}: {
  device: Device;
  login: LoginState;
  busy: boolean;
  onAction: (path: string) => void;
}) {
  const [records, setRecords] = useState<CommandRecord[]>([]);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    const load = () =>
      deviceRequest(login, `/${device.device_id}/commands?limit=12`)
        .then((result) => {
          if (active) {
            setRecords(result.commands);
            setError('');
          }
        })
        .catch(() => {
          if (active) setError('暂时无法读取执行记录');
        });
    void load();
    const timer = setInterval(() => void load(), 10000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [device.device_id, login.session?.access_token]);
  return (
    <section className="device-details" aria-label="设备详情">
      <h4>{device.name}</h4>
      <code>{device.device_id}</code>
      <p className="dialog-note">暂停保留桌面状态，继续时回到原来的工作。</p>
      <div className="device-actions">
        <button
          disabled={busy || device.state === 'changing'}
          onClick={() =>
            onAction(`/${device.device_id}/${device.state === 'online' ? 'pause' : 'resume'}`)
          }
        >
          {device.state === 'online' ? '暂停电脑' : '继续运行'}
        </button>
        <button
          disabled={busy}
          onClick={() => {
            if (
              window.confirm(
                device.preserves_files_on_revoke
                  ? '解除并停止云电脑？文件仍保留。'
                  : '解除会销毁云电脑及文件，确认已备份？',
              )
            )
              onAction(`/${device.device_id}/revoke`);
          }}
        >
          解除绑定
        </button>
      </div>
      <h4>最近执行</h4>
      {!records.length && <p className="dialog-note">还没有执行记录。</p>}
      {records.map((record) => (
        <details className="device-command" key={record.invocation_id}>
          <summary>
            <span>{record.request.capability || '创建环境'}</span>
            <time>{new Date(record.submitted_at * 1000).toLocaleTimeString()}</time>
            <span>
              {(
                {
                  running: '执行中',
                  succeeded: '已完成',
                  failed: '失败',
                  outcome_unknown: '结果未知',
                } as Record<string, string>
              )[record.status] || record.status}
            </span>
          </summary>
          <pre>{JSON.stringify(record, null, 2)}</pre>
        </details>
      ))}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
    </section>
  );
}
