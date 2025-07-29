import { describe, it, expect } from 'vitest';
import { createElementNode, FRAGMENT_TAG } from '../types';

describe('UI Tree Validation', () => {
  it('should throw error when user tries to use reserved fragment tag', () => {
    expect(() => {
      createElementNode(FRAGMENT_TAG, {}, ['Should not work']);
    }).toThrow(`The tag '${FRAGMENT_TAG}' is reserved for internal fragment nodes. Please use a different tag name.`);
  });

  it('should allow creating elements with regular tags', () => {
    expect(() => {
      createElementNode('div', {}, ['Should work fine']);
    }).not.toThrow();
  });

  it('should show the actual reserved tag name in error message', () => {
    try {
      createElementNode(FRAGMENT_TAG, {}, []);
    } catch (error) {
      expect((error as Error).message).toContain('$$fragment');
    }
  });
});