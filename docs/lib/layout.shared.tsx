import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <>
          <img
            src="/favicon.svg"
            alt=""
            aria-hidden="true"
            className="size-6"
            data-pulse-logo="true"
          />
          <span>Pulse</span>
        </>
      ),
      url: '/',
    },
    links: [
      {
        text: 'Docs',
        url: '/docs',
        active: 'nested-url',
      },
    ],
    githubUrl: 'https://github.com/erwinkn/pulse-ui',
  };
}
