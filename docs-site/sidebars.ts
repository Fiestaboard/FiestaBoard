import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    'intro',
    {
      type: 'category',
      label: 'Getting Started',
      collapsed: false,
      items: [
        'setup/quick-start',
        'setup/beginners-guide',
        'setup/first-10-minutes',
        'setup/api-keys',
      ],
    },
    {
      type: 'category',
      label: 'Using FiestaBoard',
      collapsed: false,
      items: [
        'plugins/overview',
        'plugins/configuration',
        'features/page-editor',
        'features/schedule',
        'features/silence-schedule',
      ],
    },
    {
      type: 'category',
      label: 'Plugins',
      collapsed: true,
      items: [
        'plugins/weather',
        'plugins/traffic',
        'plugins/sports-scores',
        'plugins/entertainment',
        'plugins/transit',
        'plugins/home-assistant',
      ],
    },
    {
      type: 'category',
      label: 'Deployment',
      collapsed: true,
      items: [
        'deployment/production',
        'deployment/raspberry-pi',
        'setup/docker-setup',
        'setup/cloud-api',
      ],
    },
    {
      type: 'category',
      label: 'Reference',
      collapsed: true,
      items: [
        'reference/api-endpoints',
        'reference/environment-variables',
        'reference/character-codes',
        'reference/color-guide',
      ],
    },
    {
      type: 'category',
      label: 'Development',
      collapsed: true,
      items: [
        'development/contributing',
        'development/plugin-guide',
        'development/testing',
        'setup/local-development',
      ],
    },
    'setup/v2-migration',
    'troubleshooting',
  ],
};

export default sidebars;
