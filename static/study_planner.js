document.addEventListener('DOMContentLoaded', () => {
  const titleInput = document.getElementById('titleInput');
  const dueInput = document.getElementById('dueInput');
  const addBtn = document.getElementById('addTaskBtn');
  const taskList = document.getElementById('taskList');

  async function refresh() {
    const res = await fetch('/api/planner/tasks');
    const data = await res.json();
    taskList.innerHTML = '';
    data.tasks.forEach(task => {
      const li = document.createElement('li');
      li.className = 'task-item';
      li.dataset.id = task.id;
      li.innerHTML = `
        <input type="checkbox" ${task.completed ? 'checked' : ''} class="task-complete"/>
        <span class="task-title${task.completed ? ' done' : ''}">${task.title}</span>
        <input type="date" class="task-due" value="${task.due || ''}" />
        <button class="task-delete">🗑️</button>
      `;
      taskList.appendChild(li);
    });
  }

  addBtn.addEventListener('click', async () => {
    const title = titleInput.value.trim();
    const due = dueInput.value;
    if (!title) return;
    await fetch('/api/planner/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, due })
    });
    titleInput.value = '';
    dueInput.value = '';
    await refresh();
  });

  taskList.addEventListener('change', async (e) => {
    const li = e.target.closest('li');
    const id = li.dataset.id;
    if (e.target.classList.contains('task-complete')) {
      await fetch(`/api/planner/tasks/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ completed: e.target.checked })
      });
      await refresh();
    } else if (e.target.classList.contains('task-due')) {
      await fetch(`/api/planner/tasks/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ due: e.target.value })
      });
    }
  });

  taskList.addEventListener('click', async (e) => {
    if (e.target.classList.contains('task-delete')) {
      const li = e.target.closest('li');
      const id = li.dataset.id;
      await fetch(`/api/planner/tasks/${id}`, { method: 'DELETE' });
      await refresh();
    }
  });

  refresh();
});
