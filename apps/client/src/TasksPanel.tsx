import { useEffect, useState } from 'react';
import { Sheet, IconButton } from '@hymio/ui';
import { X } from 'lucide-react';
import type { LoginState } from './useLogin';
import type { Work } from './taskModels';
import './tasks.css';

const labels: Record<string, string> = {
  queued: '等待执行',
  running: '执行中',
  waiting: '等待条件',
  paused: '已暂停',
  succeeded: '已完成',
  failed: '需要处理',
  cancelled: '已取消',
  closed: '已结束',
  active: '已安排',
};

export function TasksPanel({
  login,
  onClose,
  initialSelected = '',
}: {
  login: LoginState;
  onClose: () => void;
  initialSelected?: string;
}) {
  const [tasks, setTasks] = useState<Work[]>([]);
  const [selected, setSelected] = useState(initialSelected);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function request(data?: object) {
    if (!login.session) throw new Error('请先登录');
    const response = await fetch(login.session.backend + '/tasks', {
      method: data ? 'POST' : 'GET',
      headers: {
        Authorization: 'Bearer ' + login.session.access_token,
        'Content-Type': 'application/json',
      },
      body: data ? JSON.stringify(data) : undefined,
      signal: AbortSignal.timeout(15000),
      redirect: 'error',
    });
    if (!response.ok) throw new Error('暂时无法读取或更新任务');
    return response.json();
  }
  async function load() {
    const value = await request();
    setTasks(value.tasks);
    setError('');
  }
  useEffect(() => {
    let active = true;
    const refresh = () =>
      request()
        .then((v) => {
          if (active) {
            setTasks(v.tasks);
            setError('');
          }
        })
        .catch(() => {
          if (active) setError('暂时无法读取任务');
        });
    void refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [login.session?.access_token]);
  async function control(task: Work, action: string) {
    setBusy(true);
    try {
      await request({ action, task_id: task.id, expected_revision: task.revision });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const chosen = tasks.find((t) => t.id === selected);
  return (
    <Sheet className="tasks-dialog" labelledBy="tasks-title" onClose={onClose}>
      <header className="tasks-header">
        <div>
          <h2 id="tasks-title">任务</h2>
          <p>在对话中交代工作，这里查看进展。</p>
        </div>
        <IconButton label="关闭任务" onClick={onClose}>
          <X size={20} />
        </IconButton>
      </header>
      {error && (
        <p role="alert">
          {error}
          <button onClick={() => void load().catch((e) => setError(e.message))}>重试</button>
        </p>
      )}
      <div className="tasks-layout">
        <section aria-label="任务列表">
          {!tasks.length && <p>暂无任务。可以在对话中提出提醒、分析或持续跟进的要求。</p>}
          {tasks.map((task) => (
            <button
              key={task.id}
              onClick={() => setSelected(task.id)}
              aria-pressed={selected === task.id}
            >
              <strong>{task.title}</strong>
              <span>
                {labels[task.state === 'active' ? task.runs[0]?.status || 'active' : task.state] ||
                  task.state}
              </span>
            </button>
          ))}
        </section>
        {chosen && (
          <section className="task-detail" aria-label="任务详情">
            <h3>{chosen.title}</h3>
            <p>{chosen.objective}</p>
            <h4>完成条件</h4>
            <p>{chosen.success_criteria}</p>
            {chosen.runs.map((run) => (
              <div key={run.id}>
                <p>{labels[run.status] || run.status}</p>
                <p>{run.progress}</p>
                {run.wait_reason && <p>等待：{run.wait_reason}</p>}
                {run.result && <div style={{ whiteSpace: 'pre-wrap' }}>{run.result}</div>}
              </div>
            ))}
            {chosen.state !== 'closed' && (
              <div>
                <button
                  disabled={busy}
                  onClick={() =>
                    void control(chosen, chosen.state === 'paused' ? 'resume' : 'pause')
                  }
                >
                  {chosen.state === 'paused' ? '恢复' : '暂停'}
                </button>
                <button disabled={busy} onClick={() => void control(chosen, 'cancel')}>
                  取消任务
                </button>
              </div>
            )}
            <p>补充要求、回答问题或调整计划，请回到对话中说明。</p>
          </section>
        )}
      </div>
    </Sheet>
  );
}
