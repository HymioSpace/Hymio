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
  const [loading, setLoading] = useState(true);
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
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    void load();
    const timer = setInterval(() => void load(), 10000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [device.device_id, login.session?.access_token]);
  const isLink = device.provider === 'link';
  const paused = device.state === 'paused';
  const actionPath =
    device.state === 'missing'
      ? null
      : isLink
        ? `/${device.device_id}/${paused ? 'resume' : 'pause'}`
        : `/${device.device_id}/${device.state === 'online' ? 'pause' : 'resume'}`;
  const actionLabel =
    device.state === 'missing'
      ? '重试连接'
      : isLink
        ? paused
          ? '恢复连接'
          : '暂停连接'
        : device.state === 'online'
          ? device.provider === 'device_api'
            ? '暂停自动操作'
            : '暂停电脑'
          : device.state === 'recovery_required'
            ? '核对并继续'
            : '继续运行';
  return (
    <section className="device-details" aria-label="设备详情">
      <h4>{device.name}</h4>
      <code>{device.device_id}</code>
      <p className="dialog-note">
        {device.provider === 'link'
          ? '个人设备由本机 HymioDevice 控制。暂停会阻止新操作，解除连接会保留本机数据；已开始的操作不能撤销。'
          : device.state === 'preparing'
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
          onClick={() => (actionPath ? onAction(actionPath) : onEnsure())}
        >
          {actionLabel}
        </button>
        <button
          disabled={busy}
          onClick={() => {
            if (
              window.confirm(
                device.state === 'missing'
                  ? '移除失效设备记录？历史执行记录仍会保留。'
                  : device.preserves_files_on_revoke
                    ? '解除连接？HymioDevice 的本机文件和操作历史会保留，已开始的远程操作不能撤销。'
                    : '解除会销毁云电脑及文件，确认已备份？',
              )
            )
              onAction(`/${device.device_id}/revoke`);
          }}
        >
          {device.state === 'missing' ? '移除失效设备' : '解除连接'}
        </button>
      </div>
      <h4>最近执行</h4>
      {loading && (
        <p className="dialog-note" role="status">
          正在读取执行记录…
        </p>
      )}
      {!loading && !error && !records.length && <p className="dialog-note">还没有执行记录。</p>}
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
          {device.provider === 'link' && record.status === 'outcome_unknown' && (
            <button
              className="text-button"
              onClick={() => {
                if (
                  !window.confirm(
                    '请先在目标设备上确认操作已停止，并检查实际结果。继续后保留未知记录，但允许新的操作；不会重试原命令。',
                  )
                )
                  return;
                void deviceRequest(login, `/link/${device.device_id}/resolve`, {
                  invocation_id: record.invocation_id,
                  acknowledge_unknown: true,
                })
                  .then(() => setError('已解除执行锁，原操作仍记录为结果未知。'))
                  .catch(() => setError('暂时无法解除执行锁，请确认操作已结束。'));
              }}
            >
              我已在设备上核对，允许新操作
            </button>
          )}
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
