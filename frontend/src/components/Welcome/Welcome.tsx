import './Welcome.css';

export function Welcome() {
  return (
    <div className="welcome">
      <h2>👋 Workspace OS</h2>
      <p><strong>Выберите файл</strong> слева, чтобы начать работу.</p>
      <ul>
        <li>📁 Навигация по проектам</li>
        <li>✏️ Редактирование документов</li>
        <li>🤖 AI-ассистент</li>
        <li>📊 Отслеживание задач</li>
      </ul>
    </div>
  );
}
