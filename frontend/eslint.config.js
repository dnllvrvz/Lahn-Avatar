import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

export default [
  { ignores: ['dist'] },
  // Node.js specific configuration files
  {
    files: [
      'tailwind.config.js',
      'postcss.config.cjs.js',
      'vite.config.js',
      'eslint.config.js' // Include itself if it uses Node.js globals
    ],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
      parserOptions: {
        ecmaVersion: 'latest',
      },
    },
    rules: {
      'no-undef': 'off', // Temporarily turn off no-undef to see if globals.node is sufficient
    },
  },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...js.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]|motion|useEffect|_e|_ignoredErr' }],
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
    },
  {
    files: ['frontend/src/VoiceChatStream.jsx'],
    rules: {
      'no-unused-vars': 'off',
    },
  },
  {
    files: ['frontend/public/pcm-processor.js'],
    rules: {
      'no-unused-vars': 'off',
    },
  },
]
