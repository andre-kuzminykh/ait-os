import { useStore } from './store/useStore';
import { Sidebar } from './components/Sidebar/Sidebar';
import { Editor } from './components/Editor/Editor';
import { Dashboard } from './components/Dashboard/Dashboard';
import { Chat } from './components/Chat/Chat';
import { Welcome } from './components/Welcome/Welcome';
import './App.css';

function App() {
  const store = useStore();

  return (
    <div className="app">
      <Sidebar
        workspace={store.workspace}
        selectedPath={store.selectedPath}
        onOpenFile={store.openFile}
        onGoHome={store.goHome}
        onToggleFolder={store.toggleFolder}
        onCreateFile={store.createFile}
        onCreateFolder={store.createFolder}
      />

      <main className="main-panel">
        <div className="main-header">
          <h2>⚙️ AI Business Operating System</h2>
        </div>

        <div className="main-body">
          <div className="center-panel">
            {store.view === 'home' ? (
              <Dashboard
                tasks={store.tasks}
                onUpdateStatus={store.updateTaskStatus}
                onDeleteTask={store.deleteTask}
              />
            ) : store.selectedPath ? (
              <Editor
                selectedPath={store.selectedPath}
                openTabs={store.openTabs}
                editing={store.editing}
                content={store.getFileContent(store.selectedPath)}
                onSetEditing={store.setEditing}
                onSaveContent={store.saveContent}
                onCloseTab={store.closeTab}
                onSwitchTab={store.switchTab}
              />
            ) : (
              <Welcome />
            )}
          </div>

          <div className="right-panel">
            <Chat
              chatHistory={store.chatHistory}
              selectedPath={store.selectedPath}
              onSendMessage={store.sendMessage}
            />
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
