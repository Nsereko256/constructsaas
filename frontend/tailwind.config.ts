import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        background: '#F8F8F5',
        foreground: '#26313B',
        sidebar: '#132936',
        'sidebar-border': '#244354',
        'sidebar-accent': '#087F83',
        'sidebar-foreground': '#E4F0F0',
        muted: '#69737C',
        border: '#DDE1E3',
        primary: '#0F7075',
        warning: '#E99A11',
        critical: '#DC3C3C',
        info: '#4F86B9',
        success: '#EAF7EE',
        'success-foreground': '#2E6944',
        'success-border': '#B9DEC8',
        surface: '#F1F3F2',
        'muted-foreground': '#69737C',
      },
      fontFamily: {
        sans: ['Barlow', 'Aptos', 'Segoe UI', 'sans-serif'],
        display: ['Archivo', 'Barlow', 'sans-serif'],
      },
      borderRadius: {
        sm: '6px',
        md: '8px',
        lg: '12px',
        xl: '16px',
      },
      boxShadow: {
        panel: '0 1px 2px rgba(38, 49, 59, 0.06), 0 1px 3px rgba(38, 49, 59, 0.04)',
        lift: '0 8px 24px rgba(38, 49, 59, 0.10)',
      },
    },
  },
  plugins: [],
};

export default config;
