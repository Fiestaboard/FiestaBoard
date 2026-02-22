import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const config: Config = {
  title: 'FiestaBoard',
  tagline: 'Turn your split-flap display into a living dashboard',
  favicon: 'img/favicon.ico',

  // Future flags, see https://docusaurus.io/docs/api/docusaurus-config#future
  future: {
    v4: true, // Improve compatibility with the upcoming Docusaurus v4
  },

  // Set the production url of your site here
  url: 'https://fiestaboard.app',
  // Set the /<baseUrl>/ pathname under which your site is served
  // For GitHub pages deployment, it is often '/<projectName>/'
  baseUrl: '/',

  // GitHub pages deployment config.
  organizationName: 'Fiestaboard',
  projectName: 'fiestaboard.github.io',

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',

  // Even if you don't use internationalization, you can use this field to set
  // useful metadata like html lang.
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  headTags: [
    {
      tagName: 'meta',
      attributes: {
        name: 'keywords',
        content: 'split-flap display, dashboard, Vestaboard, weather display, stocks display, sports scores, Docker, Raspberry Pi, home automation, smart display, open source, self-hosted, WYSIWYG editor, display scheduler, IoT display, transit times, surf report, Home Assistant display',
      },
    },
    {
      tagName: 'meta',
      attributes: {
        name: 'author',
        content: 'FiestaBoard',
      },
    },
    {
      tagName: 'link',
      attributes: {
        rel: 'canonical',
        href: 'https://fiestaboard.app',
      },
    },
    {
      tagName: 'script',
      attributes: {
        type: 'application/ld+json',
      },
      innerHTML: JSON.stringify({
        '@context': 'https://schema.org',
        '@type': 'SoftwareApplication',
        name: 'FiestaBoard',
        description: 'Open-source software that transforms split-flap displays into living dashboards. Display weather, stocks, sports scores, transit times, and more.',
        url: 'https://fiestaboard.app',
        applicationCategory: 'UtilitiesApplication',
        operatingSystem: 'Linux, macOS, Windows',
        license: 'https://opensource.org/licenses/MIT',
        isAccessibleForFree: true,
        offers: {
          '@type': 'Offer',
          price: '0',
          priceCurrency: 'USD',
        },
        featureList: 'WYSIWYG page editor, Schedule mode, 18 plugins, Docker deployment, Raspberry Pi support, Weather display, Stock ticker, Sports scores, Transit times, Home Assistant integration',
        screenshot: 'https://fiestaboard.app/img/web-ui-home.png',
        softwareRequirements: 'Docker and Docker Compose',
        codeRepository: 'https://github.com/Fiestaboard/FiestaBoard',
        sourceOrganization: {
          '@type': 'Organization',
          name: 'FiestaBoard',
          url: 'https://github.com/Fiestaboard/FiestaBoard',
        },
      }),
    },
  ],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl:
            'https://github.com/Fiestaboard/FiestaBoard/tree/main/docs-site/',
        },
        blog: false, // Disable blog for now - keep it simple
        theme: {
          customCss: './src/css/custom.css',
        },
        gtag: {
          trackingID: 'G-5D2S6D6PNC',
          anonymizeIP: true,
        },
        sitemap: {
          lastmod: 'date',
          changefreq: 'weekly',
          priority: 0.5,
          filename: 'sitemap.xml',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/logo.png',
    metadata: [
      {name: 'description', content: 'FiestaBoard transforms your split-flap display into a living dashboard. Display weather, stocks, sports scores, transit times, and more with Docker deployment.'},
      {name: 'og:type', content: 'website'},
      {name: 'og:site_name', content: 'FiestaBoard'},
      {name: 'og:image', content: 'https://fiestaboard.app/img/logo.png'},
      {name: 'twitter:card', content: 'summary_large_image'},
      {name: 'twitter:title', content: 'FiestaBoard - Split-Flap Display Dashboard'},
      {name: 'twitter:description', content: 'Transform your split-flap display into a living dashboard with weather, stocks, sports, and more.'},
      {name: 'twitter:image', content: 'https://fiestaboard.app/img/logo.png'},
    ],
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'FiestaBoard',
      logo: {
        alt: 'FiestaBoard Logo',
        src: 'img/logo.png',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'tutorialSidebar',
          position: 'left',
          label: 'Documentation',
        },
        {
          href: 'https://discord.gg/wc9dDfte',
          label: 'Discord',
          position: 'right',
        },
        {
          href: 'https://github.com/Fiestaboard/FiestaBoard',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Documentation',
          items: [
            {
              label: 'Getting Started',
              to: '/docs/intro',
            },
            {
              label: 'Setup Guide',
              to: '/docs/setup/quick-start',
            },
            {
              label: 'Plugins',
              to: '/docs/plugins/overview',
            },
          ],
        },
        {
          title: 'Features',
          items: [
            {
              label: 'Page Editor',
              to: '/docs/features/page-editor',
            },
            {
              label: 'Schedule Mode',
              to: '/docs/features/schedule',
            },
            {
              label: 'API Reference',
              to: '/docs/reference/api-endpoints',
            },
            {
              label: 'Troubleshooting',
              to: '/docs/troubleshooting',
            },
          ],
        },
        {
          title: 'Community',
          items: [
            {
              label: 'Discord',
              href: 'https://discord.gg/wc9dDfte',
            },
            {
              label: 'GitHub',
              href: 'https://github.com/Fiestaboard/FiestaBoard',
            },
            {
              label: 'Issues',
              href: 'https://github.com/Fiestaboard/FiestaBoard/issues',
            },
            {
              label: 'Contributing',
              to: '/docs/development/contributing',
            },
          ],
        },
        {
          title: 'Support',
          items: [
            {
              label: 'Buy Me a Coffee',
              href: 'https://www.buymeacoffee.com/fiestaboard',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} FiestaBoard. Made with ❤️ in San Francisco.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
