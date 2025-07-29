import { describe, it, expect } from 'vitest';
import React from 'react';
import { UIRenderer } from '../UIRenderer';
import { createElementNode, createFragment, createMountPoint, FRAGMENT_TAG, isElementNode, isTextNode, isMountPointNode, getMountPointComponentKey } from '../types';
import type { UINode } from '../types';

// Lightweight tests that verify component logic without DOM rendering
describe('UIRenderer Component Logic', () => {
  it('should handle text nodes correctly', () => {
    const textNode = 'Hello World';
    expect(isTextNode(textNode)).toBe(true);
    expect(isElementNode(textNode)).toBe(false);
    
    // UIRenderer should handle this as a text node
    expect(typeof textNode).toBe('string');
  });

  it('should create element nodes with correct structure', () => {
    const elementNode = createElementNode('div', {
      className: 'test-class',
      'data-testid': 'test-div',
    }, ['Content']);

    expect(isElementNode(elementNode)).toBe(true);
    expect(isTextNode(elementNode)).toBe(false);
    expect(elementNode.tag).toBe('div');
    expect(elementNode.props.className).toBe('test-class');
    expect(elementNode.children).toHaveLength(1);
    expect(elementNode.children[0]).toBe('Content');
  });

  it('should create fragment nodes with special tag', () => {
    const fragmentNode = createFragment(['First', 'Second']);
    
    expect(isElementNode(fragmentNode)).toBe(true);
    expect(fragmentNode.tag).toBe(FRAGMENT_TAG);
    expect(fragmentNode.tag).toBe('$$fragment');
    expect(fragmentNode.props).toEqual({});
    expect(fragmentNode.children).toHaveLength(2);
    expect(fragmentNode.children[0]).toBe('First');
    expect(fragmentNode.children[1]).toBe('Second');
  });

  it('should create mount point nodes with correct structure', () => {
    const mountPointNode = createMountPoint('counter', {
      count: 5,
      color: 'blue',
      size: 'large'
    });
    
    expect(isMountPointNode(mountPointNode)).toBe(true);
    expect(isElementNode(mountPointNode)).toBe(true); // Mount points are now element nodes
    expect(isTextNode(mountPointNode)).toBe(false);
    expect(getMountPointComponentKey(mountPointNode)).toBe('counter');
    expect(mountPointNode.tag).toBe('$$counter'); // Tag contains the component key
    expect(mountPointNode.props).toEqual({
      count: 5,
      color: 'blue',
      size: 'large'
    });
    expect(mountPointNode.id).toBeDefined();
    expect(mountPointNode.children).toEqual([]); // Default empty children
  });

  it('should create mount point nodes with empty props by default', () => {
    const mountPointNode = createMountPoint('user-card');
    
    expect(isMountPointNode(mountPointNode)).toBe(true);
    expect(isElementNode(mountPointNode)).toBe(true);
    expect(getMountPointComponentKey(mountPointNode)).toBe('user-card');
    expect(mountPointNode.tag).toBe('$$user-card');
    expect(mountPointNode.props).toEqual({});
    expect(mountPointNode.children).toEqual([]);
  });

  it('should create mount point nodes with children', () => {
    const mountPointNode = createMountPoint('card', {
      title: 'Test Card'
    }, [
      'Text child',
      createElementNode('span', {}, ['Element child'])
    ]);
    
    expect(isMountPointNode(mountPointNode)).toBe(true);
    expect(getMountPointComponentKey(mountPointNode)).toBe('card');
    expect(mountPointNode.children).toHaveLength(2);
    expect(mountPointNode.children[0]).toBe('Text child');
    expect(isElementNode(mountPointNode.children[1])).toBe(true);
  });

  it('should handle nested structures correctly', () => {
    const nestedNode = createElementNode('div', { 'data-testid': 'outer' }, [
      createElementNode('span', { 'data-testid': 'inner' }, [
        'Nested content'
      ])
    ]);

    expect(nestedNode.children).toHaveLength(1);
    const innerNode = nestedNode.children[0] as any;
    expect(isElementNode(innerNode)).toBe(true);
    expect(innerNode.tag).toBe('span');
    expect(innerNode.children[0]).toBe('Nested content');
  });

  it('should handle mixed fragment content', () => {
    const fragmentNode = createFragment([
      'Text start ',
      createElementNode('strong', {}, ['bold text']),
      ' text end'
    ]);

    expect(fragmentNode.children).toHaveLength(3);
    expect(isTextNode(fragmentNode.children[0])).toBe(true);
    expect(isElementNode(fragmentNode.children[1])).toBe(true);
    expect(isTextNode(fragmentNode.children[2])).toBe(true);
    
    const strongElement = fragmentNode.children[1] as any;
    expect(strongElement.tag).toBe('strong');
    expect(strongElement.children[0]).toBe('bold text');
  });

  it('should handle complex tree structures', () => {
    const complexTree = createElementNode('div', { 'data-testid': 'root' }, [
      createElementNode('h1', {}, ['Title']),
      createFragment([
        createElementNode('p', {}, ['Paragraph 1']),
        createElementNode('p', {}, ['Paragraph 2'])
      ]),
      createElementNode('button', { type: 'button' }, ['Click me'])
    ]);

    expect(complexTree.children).toHaveLength(3);
    
    // Check h1
    const h1 = complexTree.children[0] as any;
    expect(h1.tag).toBe('h1');
    expect(h1.children[0]).toBe('Title');
    
    // Check fragment
    const fragment = complexTree.children[1] as any;
    expect(fragment.tag).toBe(FRAGMENT_TAG);
    expect(fragment.children).toHaveLength(2);
    
    // Check button
    const button = complexTree.children[2] as any;
    expect(button.tag).toBe('button');
    expect(button.props.type).toBe('button');
    expect(button.children[0]).toBe('Click me');
  });

  it('should handle empty children arrays', () => {
    const emptyElement = createElementNode('div', { 'data-testid': 'empty' }, []);
    expect(emptyElement.children).toHaveLength(0);
    expect(emptyElement.children).toEqual([]);
  });

  it('should handle empty fragments', () => {
    const emptyFragment = createFragment([]);
    expect(emptyFragment.tag).toBe(FRAGMENT_TAG);
    expect(emptyFragment.children).toHaveLength(0);
    expect(emptyFragment.children).toEqual([]);
  });

  it('should preserve keys for React reconciliation', () => {
    const nodeWithKey = createElementNode('div', { 'data-testid': 'keyed' }, []);
    nodeWithKey.key = 'unique-key';

    expect(nodeWithKey.key).toBe('unique-key');
    expect(nodeWithKey.tag).toBe('div');
  });

  it('should handle nested fragments correctly', () => {
    const nestedFragments = createElementNode('div', { 'data-testid': 'wrapper' }, [
      createFragment([
        'Start',
        createFragment([
          createElementNode('em', {}, ['emphasized']),
          ' middle '
        ]),
        'End'
      ])
    ]);

    const outerFragment = nestedFragments.children[0] as any;
    expect(outerFragment.tag).toBe(FRAGMENT_TAG);
    expect(outerFragment.children).toHaveLength(3);
    
    const innerFragment = outerFragment.children[1] as any;
    expect(innerFragment.tag).toBe(FRAGMENT_TAG);
    expect(innerFragment.children).toHaveLength(2);
    
    const emElement = innerFragment.children[0] as any;
    expect(emElement.tag).toBe('em');
    expect(emElement.children[0]).toBe('emphasized');
  });

  it('should validate reserved fragment tag usage', () => {
    expect(() => {
      createElementNode(FRAGMENT_TAG, {}, ['Should fail']);
    }).toThrow(`Tags starting with '$$' are reserved for internal use. Please use a different tag name.`);
  });

  it('should handle mixed content with mount points', () => {
    const mixedContent = createElementNode('div', { 'data-testid': 'mixed' }, [
      'Text node',
      createElementNode('span', {}, ['Element node']),
      createFragment(['Fragment', ' with ', 'multiple parts']),
      createMountPoint('counter', { count: 10 }),
      createMountPoint('user-card', { name: 'John Doe' })
    ]);

    expect(mixedContent.children).toHaveLength(5);
    
    // Check text node
    expect(isTextNode(mixedContent.children[0])).toBe(true);
    expect(mixedContent.children[0]).toBe('Text node');
    
    // Check element node
    expect(isElementNode(mixedContent.children[1])).toBe(true);
    expect((mixedContent.children[1] as any).tag).toBe('span');
    
    // Check fragment
    expect(isElementNode(mixedContent.children[2])).toBe(true);
    expect((mixedContent.children[2] as any).tag).toBe(FRAGMENT_TAG);
    
    // Check mount points
    expect(isMountPointNode(mixedContent.children[3])).toBe(true);
    expect(getMountPointComponentKey(mixedContent.children[3] as any)).toBe('counter');
    
    expect(isMountPointNode(mixedContent.children[4])).toBe(true);
    expect(getMountPointComponentKey(mixedContent.children[4] as any)).toBe('user-card');
  });

  it('should handle various node types correctly', () => {
    const nodes: UINode[] = [
      'Simple text',
      createElementNode('div', {}, []),
      createFragment(['Fragment content']),
      createElementNode('span', { className: 'test' }, ['Span with text']),
      createMountPoint('counter', { count: 5 }),
      createMountPoint('user-card')
    ];

    // Test type checking functions
    expect(isTextNode(nodes[0])).toBe(true);
    expect(isElementNode(nodes[1])).toBe(true);
    expect(isElementNode(nodes[2])).toBe(true);
    expect(isElementNode(nodes[3])).toBe(true);
    expect(isMountPointNode(nodes[4])).toBe(true);
    expect(isMountPointNode(nodes[5])).toBe(true);
    
    // Check fragment identification
    expect((nodes[2] as any).tag).toBe(FRAGMENT_TAG);
    expect((nodes[3] as any).tag).toBe('span');
    
    // Check mount point identification
    expect(getMountPointComponentKey(nodes[4] as any)).toBe('counter');
    expect(getMountPointComponentKey(nodes[5] as any)).toBe('user-card');
  });
});