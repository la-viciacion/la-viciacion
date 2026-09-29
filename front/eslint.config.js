import js from '@eslint/js';
import globals from 'globals';

export default [
  js.configs.recommended,
  {
    files: ['js/**/*.js', 'sw.js'],
    languageOptions: { ecmaVersion: 2022, sourceType: 'module', globals: { ...globals.browser, ...globals.serviceworker } },
    rules: {
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'prefer-const': 'error',
      'no-var': 'error',
    },
  },
  {
    files: ['tests/**/*.js', 'eslint.config.js'],
    languageOptions: { ecmaVersion: 2022, sourceType: 'module', globals: globals.node },
  },
  { ignores: ['node_modules/'] },
];
