import assert from 'node:assert/strict';
import test from 'node:test';
import {
  taskExecutionMode,
  taskIsCancelled,
  taskIsArchived,
  taskNeedsAttention,
  taskPortfolioScope,
  taskStatusLabel,
  taskTemporalScope,
  type Work,
} from './taskModels.ts';

function task(overrides: Partial<Work> = {}): Work {
  return {
    id: 'task-1',
    title: 'Research',
    objective: 'Find the answer',
    success_criteria: 'Evidence-backed answer',
    state: 'active',
    schedule: { mode: 'now', timezone: 'Asia/Shanghai' },
    runs: [
      {
        id: 'run-1',
        status: 'running',
        result: '',
        progress: 'Working',
        next_step: '',
        due_at: null,
        updates: [],
      },
    ],
    updated_at: 1,
    ...overrides,
  };
}

test('temporal scope stays visible when a task completes', () => {
  const completed = task({
    state: 'closed',
    close_reason: 'achieved',
    completion: 'achieve',
  });
  completed.runs[0].status = 'succeeded';
  assert.equal(taskTemporalScope(completed), 'temporary');
  assert.equal(taskPortfolioScope(completed), 'completed');

  const recurring = task({
    completion: 'maintain',
    schedule: { mode: 'daily', time: '08:00', timezone: 'Asia/Shanghai' },
  });
  assert.equal(taskTemporalScope(recurring), 'ongoing');
});

test('a successful recurring run stays in its temporal scope until the next run', () => {
  const scheduled = task({
    completion: 'maintain',
    schedule: { mode: 'daily', time: '08:00', timezone: 'Asia/Shanghai' },
    next_due_at: Date.now() / 1000 + 3600,
  });
  scheduled.runs[0].status = 'succeeded';
  assert.equal(taskTemporalScope(scheduled), 'ongoing');
  assert.equal(taskPortfolioScope(scheduled), 'ongoing');
  assert.equal(taskStatusLabel(scheduled), '已安排');
});

test('execution mode is independent from timing', () => {
  for (const mode of ['parallel_subagents', 'agent_team', 'dynamic_workflow'] as const) {
    assert.equal(taskExecutionMode(task({ execution_mode: mode })), mode);
    assert.equal(taskTemporalScope(task({ execution_mode: mode })), 'temporary');
  }
  assert.equal(taskExecutionMode(task({ executor_kind: 'program' })), 'program');
});

test('only user waits need attention and program delivery reads as sending', () => {
  const delivery = task({
    executor_kind: 'program',
    runs: [
      {
        ...task().runs[0],
        status: 'waiting',
        wait_kind: null,
      },
    ],
  });
  assert.equal(taskNeedsAttention(delivery), false);
  assert.equal(taskStatusLabel(delivery), '发送中');

  const question = task({
    runs: [
      {
        ...task().runs[0],
        status: 'waiting',
        wait_kind: 'user',
      },
    ],
  });
  assert.equal(taskNeedsAttention(question), true);
  assert.equal(taskStatusLabel(question), '等待你回复');
});

test('cancelled tasks are not successes and can be removed from the active list', () => {
  const cancelled = task({
    state: 'closed',
    close_reason: 'cancelled',
  });
  cancelled.runs[0].status = 'cancelled';
  assert.equal(taskIsCancelled(cancelled), true);
  assert.equal(taskStatusLabel(cancelled), '已取消');
  assert.equal(taskIsArchived(cancelled), true);
});
