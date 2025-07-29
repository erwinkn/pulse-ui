import { useState, useRef } from 'react';
import { ReactiveUIContainer, EventEmitterTransport } from '~/ui-tree';
import { ComponentRegistryProvider, type ComponentRegistry } from '~/ui-tree/component-registry';
import type { UIElementNode, UIUpdatePayload } from '~/ui-tree/types';
import { createElementNode, createFragment, createMountPoint } from '~/ui-tree/types';
import { Counter, UserCard, ProgressBar, StatusBadge, MetricCard } from '~/ui-tree/demo-components';

export default function Demo() {
  const transportRef = useRef(new EventEmitterTransport());
  const [counter, setCounter] = useState(0);
  const [messages, setMessages] = useState<string[]>([]);
  const [userOnline, setUserOnline] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusType, setStatusType] = useState<'success' | 'warning' | 'error' | 'info'>('info');

  // Component registry for mount points
  const componentRegistry: ComponentRegistry = {
    'counter': Counter,
    'user-card': UserCard,
    'progress-bar': ProgressBar,
    'status-badge': StatusBadge,
    'metric-card': MetricCard,
  };

  const [initialTree] = useState(() => 
    createElementNode('div', { 
      className: 'p-8 max-w-4xl mx-auto space-y-6',
      style: { fontFamily: 'Inter, sans-serif' }
    }, [
      createElementNode('h1', { 
        className: 'text-4xl font-bold text-gray-800 mb-4',
        id: 'main-title'
      }, [
        '🚀 Reactive UI Tree with Mount Points Demo'
      ]),
      
      // Mount Points Section
      createElementNode('div', {
        className: 'bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg p-6',
        id: 'mount-points-section'
      }, [
        createElementNode('h2', { 
          className: 'text-2xl font-semibold text-gray-800 mb-6 text-center'
        }, [
          'External React Components via Mount Points'
        ]),
        
        // Grid of mount point components
        createElementNode('div', {
          className: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6'
        }, [
          createMountPoint('counter', {
            count: 0,
            label: 'Server Counter',
            color: 'blue',
            size: 'md'
          }),
          createMountPoint('user-card', {
            name: 'Alice Johnson',
            email: 'alice@example.com',
            role: 'Frontend Developer',
            status: 'offline'
          }),
          createMountPoint('progress-bar', {
            value: 0,
            max: 100,
            label: 'Project Progress',
            color: 'green',
            showPercentage: true
          })
        ]),
        
        createElementNode('div', {
          className: 'flex flex-wrap gap-4 justify-center'
        }, [
          createMountPoint('status-badge', {
            status: 'info',
            text: 'System Status',
            size: 'md',
            pulse: false
          }),
          createMountPoint('metric-card', {
            title: 'Active Users',
            value: 1250,
            change: 12.5,
            trend: 'up',
            icon: '👥'
          })
        ])
      ]),

      // Traditional Elements Section
      createElementNode('div', { 
        className: 'bg-blue-50 border border-blue-200 rounded-lg p-6',
        id: 'traditional-content'
      }, [
        createElementNode('h2', { 
          className: 'text-2xl font-semibold text-blue-800 mb-4'
        }, [
          'Traditional UI Elements'
        ]),
        createElementNode('p', { 
          className: 'text-blue-700 mb-4',
          id: 'counter-display'
        }, [
          'Legacy Counter: 0'
        ]),
        createElementNode('div', { 
          className: 'space-y-2',
          id: 'message-list'
        }, [])
      ]),
      
      createElementNode('div', { 
        className: 'bg-gray-50 border border-gray-200 rounded-lg p-4'
      }, [
        createElementNode('h3', { 
          className: 'text-lg font-semibold text-gray-800 mb-2'
        }, [
          'Features Demonstrated'
        ]),
        createElementNode('ul', { 
          className: 'list-disc list-inside space-y-1 text-gray-700 text-sm'
        }, [
          createElementNode('li', {}, ['Mount points for external React components']),
          createElementNode('li', {}, ['Component prop updates via server']),
          createElementNode('li', {}, ['Text content updates']),
          createElementNode('li', {}, ['Dynamic element insertion']),
          createElementNode('li', {}, ['Props updates with styling changes']),
          createElementNode('li', {}, ['Efficient re-rendering with React.memo'])
        ])
      ])
    ])
  );

  const sendUpdate = (update: UIUpdatePayload) => {
    transportRef.current.dispatchMessage({
      type: 'ui_updates',
      updates: [update]
    });
  };

  // Mount point update functions
  const updateMountPointCounter = () => {
    const newCounter = counter + 1;
    setCounter(newCounter);
    
    sendUpdate({
      id: `mount-counter-update-${Date.now()}`,
      type: 'update_props',
      path: [1, 1, 0], // mount-points-section > grid > counter mount point
      data: { 
        props: { 
          count: newCounter,
          label: 'Server Counter',
          color: newCounter % 2 === 0 ? 'blue' : 'green',
          size: 'md'
        } 
      }
    });
  };

  const toggleUserStatus = () => {
    const newStatus = userOnline ? 'offline' : 'online';
    setUserOnline(!userOnline);
    
    sendUpdate({
      id: `user-status-update-${Date.now()}`,
      type: 'update_props',
      path: [1, 1, 1], // mount-points-section > grid > user-card mount point
      data: { 
        props: { 
          name: 'Alice Johnson',
          email: 'alice@example.com',
          role: 'Frontend Developer',
          status: newStatus
        } 
      }
    });
  };

  const updateProgress = () => {
    const newProgress = (progress + 25) % 125; // Cycle 0, 25, 50, 75, 100, 0...
    setProgress(newProgress);
    
    sendUpdate({
      id: `progress-update-${Date.now()}`,
      type: 'update_props',
      path: [1, 1, 2], // mount-points-section > grid > progress-bar mount point
      data: { 
        props: { 
          value: newProgress,
          max: 100,
          label: 'Project Progress',
          color: newProgress > 75 ? 'green' : newProgress > 50 ? 'blue' : 'red',
          showPercentage: true
        } 
      }
    });
  };

  const cycleStatus = () => {
    const statuses: Array<'success' | 'warning' | 'error' | 'info'> = ['info', 'success', 'warning', 'error'];
    const currentIndex = statuses.indexOf(statusType);
    const nextStatus = statuses[(currentIndex + 1) % statuses.length];
    setStatusType(nextStatus);
    
    const statusTexts = {
      info: 'System Info',
      success: 'All Good!',
      warning: 'Warning',
      error: 'Error!'
    };
    
    sendUpdate({
      id: `status-update-${Date.now()}`,
      type: 'update_props',
      path: [1, 2, 0], // mount-points-section > bottom-row > status-badge mount point
      data: { 
        props: { 
          status: nextStatus,
          text: statusTexts[nextStatus],
          size: 'md',
          pulse: nextStatus === 'error'
        } 
      }
    });
  };

  const updateMetrics = () => {
    const users = Math.floor(Math.random() * 2000) + 1000;
    const change = (Math.random() - 0.5) * 40; // -20% to +20%
    const trend = change > 0 ? 'up' : change < 0 ? 'down' : 'neutral';
    
    sendUpdate({
      id: `metrics-update-${Date.now()}`,
      type: 'update_props',
      path: [1, 2, 1], // mount-points-section > bottom-row > metric-card mount point
      data: { 
        props: { 
          title: 'Active Users',
          value: users,
          change: Math.abs(change),
          trend: trend,
          icon: '👥'
        } 
      }
    });
  };

  // Legacy functions for traditional elements
  const incrementCounter = () => {
    const newCounter = counter + 1;
    setCounter(newCounter);
    
    sendUpdate({
      id: `counter-update-${Date.now()}`,
      type: 'replace',
      path: [2, 1, 0], // traditional-content > counter-display > text
      data: { node: `Legacy Counter: ${newCounter}` }
    });
  };

  const addMessage = () => {
    const message = `Message added at ${new Date().toLocaleTimeString()}`;
    const newMessages = [...messages, message];
    setMessages(newMessages);
    
    sendUpdate({
      id: `message-update-${Date.now()}`,
      type: 'insert',
      path: [2, 2], // traditional-content > message-list
      data: {
        node: createElementNode('div', { 
          className: 'p-2 bg-white border border-blue-200 rounded text-sm text-blue-800',
          key: `message-${Date.now()}`
        }, [
          message
        ]),
        index: newMessages.length - 1
      }
    });
  };

  const changeStyle = () => {
    const colorClassMap: Record<string, string> = {
      blue:   'bg-blue-50 border border-blue-200 rounded-lg p-6',
      green:  'bg-green-50 border border-green-200 rounded-lg p-6',
      purple: 'bg-purple-50 border border-purple-200 rounded-lg p-6',
      red:    'bg-red-50 border border-red-200 rounded-lg p-6',
      yellow: 'bg-yellow-50 border border-yellow-200 rounded-lg p-6',
    };
    const colors = Object.keys(colorClassMap);
    const randomColor = colors[Math.floor(Math.random() * colors.length)];

    sendUpdate({
      id: `style-update-${Date.now()}`,
      type: 'update_props',
      path: [2], // traditional-content
      data: {
        props: { 
          className: colorClassMap[randomColor],
          id: 'traditional-content'
        }
      }
    });
  };

  const updateTitle = () => {
    const titles = [
      '🚀 Reactive UI Tree with Mount Points Demo',
      '⚡ Server-Driven Components in Action!',
      '🔥 Mount Points + React = Magic',
      '✨ External Components Made Simple',
      '🎯 Dynamic Component Updates'
    ];
    const randomTitle = titles[Math.floor(Math.random() * titles.length)];
    
    sendUpdate({
      id: `title-update-${Date.now()}`,
      type: 'replace',
      path: [0, 0], // main-title > text
      data: { node: randomTitle }
    });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto p-8">
        {/* Control Panel */}
        <div className="bg-white border border-gray-300 rounded-lg p-6 mb-6 shadow-sm">
          <h2 className="text-xl font-semibold text-gray-800 mb-4">
            Demo Controls (External to ReactiveUIContainer)
          </h2>
          
          {/* Mount Point Controls */}
          <div className="mb-4">
            <h3 className="text-lg font-medium text-gray-700 mb-2">Mount Point Component Updates</h3>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={updateMountPointCounter}
                className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
              >
                Update Counter Component
              </button>
              <button
                onClick={toggleUserStatus}
                className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
              >
                Toggle User Status
              </button>
              <button
                onClick={updateProgress}
                className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 transition-colors"
              >
                Update Progress
              </button>
              <button
                onClick={cycleStatus}
                className="px-4 py-2 bg-yellow-600 text-white rounded hover:bg-yellow-700 transition-colors"
              >
                Cycle Status Badge
              </button>
              <button
                onClick={updateMetrics}
                className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 transition-colors"
              >
                Update Metrics
              </button>
            </div>
          </div>

          {/* Traditional Element Controls */}
          <div>
            <h3 className="text-lg font-medium text-gray-700 mb-2">Traditional Element Updates</h3>
            <div className="flex flex-wrap gap-3">
              <button
                onClick={incrementCounter}
                className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
              >
                Legacy Counter
              </button>
              <button
                onClick={addMessage}
                className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
              >
                Add Message
              </button>
              <button
                onClick={changeStyle}
                className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
              >
                Change Style
              </button>
              <button
                onClick={updateTitle}
                className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
              >
                Update Title
              </button>
            </div>
          </div>

          <p className="text-sm text-gray-600 mt-4">
            The mount point buttons update React component props via server-side UI tree updates, 
            demonstrating seamless integration of external components with server-rendered UI.
          </p>
        </div>

        {/* ReactiveUIContainer with Component Registry */}
        <div className="border-2 border-dashed border-gray-400 rounded-lg p-1">
          <div className="text-xs text-gray-500 mb-2 px-2">ReactiveUIContainer with ComponentRegistry boundary:</div>
          <ComponentRegistryProvider registry={componentRegistry}>
            <ReactiveUIContainer 
              initialTree={initialTree} 
              transport={transportRef.current}
              onMessage={(message) => {
                console.log('Received transport message:', message);
              }}
            />
          </ComponentRegistryProvider>
        </div>
      </div>
    </div>
  );
}