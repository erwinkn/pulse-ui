import { useState, useRef } from 'react';
import { ReactiveUIContainer, EventEmitterTransport } from '~/ui-tree';
import type { UIElementNode, UIUpdatePayload } from '~/ui-tree/types';
import { createElementNode, createFragment } from '~/ui-tree/types';

export default function Demo() {
  const transportRef = useRef(new EventEmitterTransport());
  const [counter, setCounter] = useState(0);
  const [messages, setMessages] = useState<string[]>([]);

  const [initialTree] = useState(() => 
    createElementNode('div', { 
      className: 'p-8 max-w-4xl mx-auto space-y-6',
      style: { fontFamily: 'Inter, sans-serif' }
    }, [
      createElementNode('h1', { 
        className: 'text-4xl font-bold text-gray-800 mb-4',
        id: 'main-title'
      }, [
        'Interactive Reactive UI Tree Demo'
      ]),
      createElementNode('div', { 
        className: 'bg-blue-50 border border-blue-200 rounded-lg p-6',
        id: 'demo-content'
      }, [
        createElementNode('h2', { 
          className: 'text-2xl font-semibold text-blue-800 mb-4'
        }, [
          'Dynamic Content Area'
        ]),
        createElementNode('p', { 
          className: 'text-blue-700 mb-4',
          id: 'counter-display'
        }, [
          'Counter: 0'
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
          createElementNode('li', {}, ['Text content updates']),
          createElementNode('li', {}, ['Dynamic element insertion']),
          createElementNode('li', {}, ['Props updates with styling changes']),
          createElementNode('li', {}, ['Efficient re-rendering with React.memo']),
          createElementNode('li', {}, ['Transport layer abstraction'])
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

  const incrementCounter = () => {
    const newCounter = counter + 1;
    setCounter(newCounter);
    
    sendUpdate({
      id: `counter-update-${Date.now()}`,
      type: 'replace',
      path: [1, 1, 0], // demo-content > counter-display > text
      data: { node: `Counter: ${newCounter}` }
    });
  };

  const addMessage = () => {
    const message = `Message added at ${new Date().toLocaleTimeString()}`;
    const newMessages = [...messages, message];
    setMessages(newMessages);
    
    sendUpdate({
      id: `message-update-${Date.now()}`,
      type: 'insert',
      path: [1, 2], // demo-content > message-list
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
      path: [1], // demo-content
      data: {
        props: { 
          className: colorClassMap[randomColor],
          id: 'demo-content'
        }
      }
    });
  };

  const updateTitle = () => {
    const titles = [
      'Interactive Reactive UI Tree Demo',
      '🚀 Real-time UI Updates in Action!',
      '⚡ Lightning Fast React Rendering',
      '🔥 Server-Driven UI Made Simple',
      '✨ Dynamic Updates Without Full Rerenders'
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
          <div className="flex flex-wrap gap-3">
            <button
              onClick={incrementCounter}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
            >
              Increment Counter
            </button>
            <button
              onClick={addMessage}
              className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
            >
              Add Message
            </button>
            <button
              onClick={changeStyle}
              className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 transition-colors"
            >
              Change Style
            </button>
            <button
              onClick={updateTitle}
              className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
            >
              Update Title
            </button>
          </div>
          <p className="text-sm text-gray-600 mt-3">
            These buttons send updates through the transport layer to the ReactiveUIContainer below.
            Watch how the UI updates efficiently without full page rerenders!
          </p>
        </div>

        {/* ReactiveUIContainer */}
        <div className="border-2 border-dashed border-gray-400 rounded-lg p-1">
          <div className="text-xs text-gray-500 mb-2 px-2">ReactiveUIContainer boundary:</div>
          <ReactiveUIContainer 
            initialTree={initialTree} 
            transport={transportRef.current}
            onMessage={(message) => {
              console.log('Received transport message:', message);
            }}
          />
        </div>
      </div>
    </div>
  );
}