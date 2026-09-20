import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', '../adguard_log_viewer/app/static'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],

      // This app fetches in effects on purpose: it has no data-fetching
      // library, and the requests it makes are genuinely a subscription to an
      // external system (the app's API). The rule assumes a React Query
      // style setup, which would be a dependency this app does not need.
      'react-hooks/set-state-in-effect': 'off',

      // TanStack Virtual returns fresh closures by design; the React Compiler
      // only warns that it will not memoise the component around it.
      'react-hooks/incompatible-library': 'off',
    },
  },
);
