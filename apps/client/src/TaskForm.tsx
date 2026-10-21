import { useState } from 'react';
import { createIdentity } from '@hymio/client';
import { ArrowLeft, ArrowUpRight, CalendarDays } from 'lucide-react';
import { Button } from '@hymio/ui';
import type { Work } from './taskModels';

export function TaskForm({
  task,
  busy,
  onCancel,
  onSave,
}: {
  task?: Work;
  busy: boolean;
  onCancel: () => void;
  onSave: (data: object) => void;
}) {
  const [title, setTitle] = useState(task?.title || ''),
    [objective, setObjective] = useState(task?.objective || ''),
    [criteria, setCriteria] = useState(task?.success_criteria || '');
  const [mode, setMode] = useState(task?.schedule.mode || 'now'),
    [at, setAt] = useState(
      task?.schedule.at
        ? new Date(new Date(task.schedule.at).getTime() - new Date().getTimezoneOffset() * 60000)
            .toISOString()
            .slice(0, 16)
        : '',
    ),
    [time, setTime] = useState(task?.schedule.time || '09:00'),
    [day, setDay] = useState(task?.schedule.weekday || 0);
  const [kind, setKind] = useState(task?.kind || 'task');
  const [grace, setGrace] = useState(task?.schedule.grace_seconds ?? 900);
  const [requestId] = useState(createIdentity);
  const zone = task?.schedule.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  return (
    <form
      className="task-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({
          action: task ? 'edit' : 'create',
          request_id: requestId,
          ...(task ? { task_id: task.id } : {}),
          title,
          kind,
          objective,
          success_criteria: criteria,
          schedule: {
            mode,
            timezone: zone,
            grace_seconds: grace,
            run_timeout_seconds: task?.schedule.run_timeout_seconds ?? 3600,
            ...(mode === 'once' ? { at: new Date(at).toISOString() } : {}),
            ...(['daily', 'weekly'].includes(mode) ? { time } : {}),
            ...(mode === 'weekly' ? { weekday: day } : {}),
          },
        });
      }}
    >
      <button type="button" className="task-back" onClick={onCancel}>
        <ArrowLeft size={15} />
        返回任务
      </button>
      <h3>{task ? '调整这件事' : '想让 Hymio 做什么？'}</h3>
      <label>
        类型
        <select value={kind} onChange={(e) => setKind(e.target.value as 'task' | 'reminder')}>
          <option value="task">推进一件事</option>
          <option value="reminder">提醒我</option>
        </select>
      </label>
      <label>
        允许迟到
        <select value={grace} onChange={(e) => setGrace(Number(e.target.value))}>
          {[...new Set([60, 300, 900, 3600, grace])]
            .sort((a, b) => a - b)
            .map((seconds) => (
              <option key={seconds} value={seconds}>
                {seconds / 60} 分钟内补执行
              </option>
            ))}
        </select>
        <small>超过后标记已过期，不再执行这一次。</small>
      </label>
      <label>
        一个清楚的名字
        <input
          required
          maxLength={160}
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="例如，整理每周值得关注的 AI 进展"
        />
      </label>
      <label>
        要做什么
        <textarea
          required
          rows={3}
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
          placeholder="给一些背景、范围，以及你关心的重点。"
        />
      </label>
      <label>
        怎样算完成
        <input
          required
          value={criteria}
          onChange={(e) => setCriteria(e.target.value)}
          placeholder="例如，5 条附来源的摘要，并说明与我的关联。"
        />
      </label>
      <fieldset>
        <legend>
          <CalendarDays size={15} />
          什么时候开始
        </legend>
        <div className="task-schedule-choices">
          {[
            ['now', '现在'],
            ['once', '选个时间'],
            ['daily', '每天'],
            ['weekly', '每周'],
          ].map(([key, label]) => (
            <button
              type="button"
              key={key}
              aria-pressed={mode === key}
              onClick={() => setMode(key)}
            >
              {label}
            </button>
          ))}
        </div>
        {mode === 'once' && (
          <input
            aria-label="执行时间"
            required
            type="datetime-local"
            value={at}
            onChange={(e) => setAt(e.target.value)}
          />
        )}
        {['daily', 'weekly'].includes(mode) && (
          <div className="task-schedule-time">
            {mode === 'weekly' && (
              <select
                aria-label="每周哪一天"
                value={day}
                onChange={(e) => setDay(Number(e.target.value))}
              >
                {['周一', '周二', '周三', '周四', '周五', '周六', '周日'].map((d, i) => (
                  <option key={d} value={i}>
                    {d}
                  </option>
                ))}
              </select>
            )}
            <input
              type="time"
              aria-label="执行时间"
              required
              value={time}
              onChange={(e) => setTime(e.target.value)}
            />
          </div>
        )}
        <small>{zone} · 工作会在云端执行，无需保持页面打开。</small>
      </fieldset>
      <div className="task-form-submit">
        <Button type="button" variant="quiet" onClick={onCancel}>
          取消
        </Button>
        <Button type="submit" busy={busy}>
          {task ? '保存安排' : '交给 Hymio'}
          <ArrowUpRight size={15} />
        </Button>
      </div>
    </form>
  );
}
