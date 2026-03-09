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

  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },

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
        content: 'split-flap display, split-flap display software, dashboard, Vestaboard, Vestaboard software, Vestaboard app, Vestaboard dashboard, Vestaboard Home Assistant, Vestaboard plugins, best software for Vestaboard, weather display, stocks display, sports scores, Docker, Raspberry Pi, home automation, smart display, open source, self-hosted, WYSIWYG editor, display scheduler, IoT display, transit times, surf report, Home Assistant display, split-flap display app, display plugins, FiestaBoard',
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
        alternateName: ['FiestaBoard Split-Flap Display Software', 'FiestaBoard Dashboard'],
        description: 'Open-source software for split-flap displays. Adds plugins, scheduling, and a visual page editor to your board. Compatible with Vestaboard Flagship and Note.',
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
        featureList: 'WYSIWYG page editor, Schedule mode, 23 plugins, Docker deployment, Raspberry Pi support, Weather display, Stock ticker, Sports scores, Transit times, Home Assistant integration',
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
    {
      tagName: 'script',
      attributes: {
        type: 'application/ld+json',
      },
      innerHTML: JSON.stringify({
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        mainEntity: [
          {
            '@type': 'Question',
            name: 'What is FiestaBoard?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'FiestaBoard is free, open-source software for split-flap displays. It adds 23 data plugins, a visual page editor, and scheduling to your board. Compatible with Vestaboard Flagship and Note.',
            },
          },
          {
            '@type': 'Question',
            name: 'Is FiestaBoard free?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'Yes. FiestaBoard is completely free and open source under the MIT license. There are no subscriptions, paid tiers, or usage limits.',
            },
          },
          {
            '@type': 'Question',
            name: 'How do I install FiestaBoard?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'FiestaBoard runs in Docker. Pull the image from Docker Hub and start it with docker-compose — you can be up and running in under 5 minutes. It works on Mac, Windows, Linux, and Raspberry Pi.',
            },
          },
          {
            '@type': 'Question',
            name: 'What can FiestaBoard display on my board?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'FiestaBoard has 23 built-in plugins for weather, stocks, sports scores, transit times, Disney park wait times, aircraft tracking, surf conditions, Home Assistant integration, and more. Many plugins require no API key.',
            },
          },
          {
            '@type': 'Question',
            name: 'Does FiestaBoard work with Vestaboard?',
            acceptedAnswer: {
              '@type': 'Answer',
              text: 'Yes. FiestaBoard is compatible with Vestaboard Flagship (22x6) and Vestaboard Note (15x3). It connects via the Vestaboard Local API (recommended, supports animations) or the Vestaboard Cloud API (works remotely). FiestaBoard runs alongside the official Vestaboard app.',
            },
          },
        ],
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
          versions: {
            current: {
              label: 'Next 🚧',
              banner: 'unreleased',
            },
          },
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
      {name: 'description', content: 'FiestaBoard is free, open-source software for split-flap displays. Add weather, stocks, sports scores, transit times, and more with 23 plugins, a visual editor, and scheduling. Compatible with Vestaboard.'},
      {name: 'og:type', content: 'website'},
      {name: 'og:site_name', content: 'FiestaBoard'},
      {name: 'og:image', content: 'https://fiestaboard.app/img/logo.png'},
      {name: 'twitter:card', content: 'summary_large_image'},
      {name: 'twitter:title', content: 'FiestaBoard — Split-Flap Display Software'},
      {name: 'twitter:description', content: 'Free, open-source software for split-flap displays. 23 plugins, visual editor, scheduling. Compatible with Vestaboard.'},
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
          type: 'dropdown',
          label: 'Documentation',
          position: 'left',
          items: [
            {type: 'doc', docId: 'intro', label: 'Getting Started'},
            {type: 'doc', docId: 'setup/quick-start', label: 'Setup'},
            {type: 'doc', docId: 'features/page-editor', label: 'Features'},
            {type: 'doc', docId: 'plugins/overview', label: 'Plugins'},
            {type: 'doc', docId: 'deployment/production', label: 'Deployment'},
            {type: 'doc', docId: 'development/contributing', label: 'Development'},
            {type: 'doc', docId: 'reference/api-endpoints', label: 'API Reference'},
            {type: 'doc', docId: 'troubleshooting', label: 'Troubleshooting'},
          ],
        },
        {
          type: 'docsVersionDropdown',
          position: 'left',
        },
        {
          href: 'https://hub.docker.com/r/fiestaboard/fiestaboard',
          label: 'Docker Hub',
          position: 'right',
        },
        {
          href: 'https://discord.gg/ujasGntNhQ',
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
              label: 'Docker Hub',
              href: 'https://hub.docker.com/r/fiestaboard/fiestaboard',
            },
            {
              label: 'Discord',
              href: 'https://discord.gg/ujasGntNhQ',
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
              label: 'Buy a Vestaboard ($200 off)',
              href: 'https://fiestaboard.app/buyavestaboard',
            },
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
