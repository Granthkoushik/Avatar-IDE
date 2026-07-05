export default [
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        document: "readonly",
        window: "readonly",
        fetch: "readonly",
        navigator: "readonly",
        performance: "readonly",
        TextDecoder: "readonly",
        monaco: "readonly",
        require: "readonly",
        localStorage: "readonly",
        clearTimeout: "readonly",
        setTimeout: "readonly"
      }
    },
    rules: {
      "no-unused-vars": "warn",
      "no-undef": "error"
    }
  }
];
