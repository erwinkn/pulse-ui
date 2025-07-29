import { describe, it, expect } from 'vitest';
import type { UIElementNode, UIUpdatePayload } from '../types';
import { createElementNode, createFragment } from '../types';
import { applyUpdates } from '../update-utils';

describe('UI Tree Integration', () => {
  it('should handle a complete workflow of updates', () => {
    // Create initial tree using simplified structure
    const initialTree = createElementNode('div', { className: 'container' }, [
      createElementNode('h1', {}, ['Title']),
      createElementNode('p', {}, ['Content'])
    ]);

    // Apply a series of updates like a real application would
    const updates: UIUpdatePayload[] = [
      // Replace the title text (since we no longer have update_text)
      {
        id: 'update-1',
        type: 'replace',
        path: [0, 0],
        data: { node: 'Updated Title' }
      },
      // Add a new paragraph
      {
        id: 'update-2',
        type: 'insert',
        path: [],
        data: {
          node: createElementNode('p', { className: 'new-paragraph' }, [
            'New paragraph added dynamically'
          ]),
          index: 2
        }
      },
      // Update container props
      {
        id: 'update-3',
        type: 'update_props',
        path: [],
        data: {
          props: { className: 'container updated', id: 'main-container' }
        }
      }
    ];

    const updatedTree = applyUpdates(initialTree, updates);

    // Verify the updates were applied correctly
    expect((updatedTree as UIElementNode).props.className).toBe('container updated');
    expect((updatedTree as UIElementNode).props.id).toBe('main-container');
    expect((updatedTree as UIElementNode).children).toHaveLength(3);
    
    // Check title was updated (text is now a string)
    const titleText = ((updatedTree as UIElementNode).children[0] as UIElementNode).children[0];
    expect(titleText).toBe('Updated Title');
    
    // Check new paragraph was added
    const newParagraph = (updatedTree as UIElementNode).children[2] as UIElementNode;
    expect(newParagraph.tag).toBe('p');
    expect(newParagraph.props.className).toBe('new-paragraph');
    
    const newParagraphText = newParagraph.children[0];
    expect(newParagraphText).toBe('New paragraph added dynamically');
  });

  it('should work with fragments', () => {
    // Test the fragment functionality
    const initialTree = createElementNode('div', {}, [
      createFragment(['Hello', ' ', 'World'])
    ]);

    const updates: UIUpdatePayload[] = [
      // Insert a new text node into the fragment
      {
        id: 'update-1',
        type: 'insert',
        path: [0],
        data: { node: '!', index: 3 }
      }
    ];

    const updatedTree = applyUpdates(initialTree, updates);
    const fragment = (updatedTree as UIElementNode).children[0] as UIElementNode;
    
    expect(fragment.children).toHaveLength(4);
    expect(fragment.children[0]).toBe('Hello');
    expect(fragment.children[1]).toBe(' ');
    expect(fragment.children[2]).toBe('World');
    expect(fragment.children[3]).toBe('!');
  });
});