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
  onEnsure,
}: {
  device: Device;
  login: LoginState;
  busy: boolean;
  onAction: (path: string) => void;
  onEnsure: () => void;
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
      <p className="dialog-note">
        {device.state === 'preparing'
          ? '正在自动准备云电脑，无需手动绑定。'
          : device.replaces_device_id
            ? '原环境已失效，系统已自动更换为空环境。旧文件未恢复，聊天记录保留。'
            : device.state === 'missing'
              ? '原沙箱已不存在，无法继续运行。系统会自动绑定新环境；原沙箱文件无法恢复，聊天记录仍保留。'
              : '到期自动暂停，继续时回到原来的工作。'}
      </p>
      <div className="device-actions">
        <button
          disabled={busy || ['changing', 'preparing'].includes(device.state)}
          onClick={() =>
            device.state === 'missing'
              ? onEnsure()
              : onAction(`/${device.device_id}/${device.state === 'online' ? 'pause' : 'resume'}`)
          }
        >
          {device.state === 'missing'
            ? '重试连接'
            : device.state === 'online'
              ? '暂停电脑'
              : '继续运行'}
        </button>
        <button
          disabled={busy}
          onClick={() => {
            if (
              window.confirm(
                device.state === 'missing'
                  ? '移除失效设备记录？历史执行记录仍会保留。'
                  : device.preserves_files_on_revoke
                    ? '解除并停止云电脑？文件仍保留。'
                    : '解除会销毁云电脑及文件，确认已备份？',
              )
            )
              onAction(`/${device.device_id}/revoke`);
          }}
        >
          {device.state === 'missing' ? '移除失效设备' : '解除绑定'}
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
