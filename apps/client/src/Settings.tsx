import { useState } from 'react';
import { ConnectionsPanel } from './ConnectionsPanel';
import { ModelSettings } from './ModelSettings';
import { ToolPermissionSettings } from './ToolPermissionSettings';
import { displayName } from './HomePanel';
import { Activity, LogOut, X } from 'lucide-react';
import type { LoginState } from './useLogin';
import { DeviceManager } from './DeviceManager';
import { Button, Companion, IconButton, Sheet } from '@hymio/ui';
export function Settings({
  login,
  onClose,
  onTrace,
}: {
  login: LoginState;
  onClose: () => void;
  onTrace: () => void;
}) {
  const [connections, setConnections] = useState(false);
  const [confirmLogout, setConfirmLogout] = useState(false);
  if (connections)
    return (
      <Sheet className="settings-dialog" labelledBy="connections-title" onClose={onClose}>
        <h2 id="connections-title" className="sr-only">
          连接来源
        </h2>
        <ConnectionsPanel login={login} onBack={() => setConnections(false)} />
      </Sheet>
    );
  return (
    <Sheet className="settings-dialog" labelledBy="settings-title" onClose={onClose}>
      <div className="dialog-head">
        <Companion compact />
        <IconButton label="关闭账号设置" onClick={onClose}>
          <X size={19} />
        </IconButton>
      </div>
      <h2 id="settings-title">账号与偏好</h2>
      <p className="dialog-intro">{displayName(login.session?.name)}</p>
      <p className="dialog-note">在不同设备上，继续同一段对话。</p>
      <button className="settings-trace" onClick={() => setConnections(true)}>
        连接来源 · 邮件、清单与日常
      </button>
      <ModelSettings login={login} />
      <ToolPermissionSettings login={login} />
      <DeviceManager login={login} />
      {login.error && (
        <p role="alert" className="form-error">
          {login.error}
        </p>
      )}
      <button className="settings-trace" onClick={onTrace}>
        <Activity size={16} />
        工作记录与连接诊断
      </button>
      <Button variant="quiet" busy={login.busy} onClick={() => setConfirmLogout(true)}>
        退出登录
      </Button>
      {confirmLogout && (
        <div
          className="logout-confirm-backdrop"
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              event.stopPropagation();
              setConfirmLogout(false);
            }
          }}
        >
          <section
            className="logout-confirm"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="logout-confirm-title"
            aria-describedby="logout-confirm-detail"
          >
            <div className="logout-confirm-icon" aria-hidden="true">
              <LogOut size={23} strokeWidth={1.8} />
            </div>
            <h3 id="logout-confirm-title">退出当前账号</h3>
            <p id="logout-confirm-detail">
              本机对话缓存和待发送内容会清除；云端的任务、记忆和连接不会删除。
            </p>
            <div className="logout-confirm-actions">
              <Button onClick={() => setConfirmLogout(false)} autoFocus>
                取消
              </Button>
              <Button
                className="logout-confirm-primary"
                busy={login.busy}
                onClick={() => void login.logout()}
              >
                退出登录
              </Button>
            </div>
          </section>
        </div>
      )}
    </Sheet>
  );
}
