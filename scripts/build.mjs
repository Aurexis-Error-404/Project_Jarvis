import * as esbuild from 'esbuild';

const args = process.argv.slice(2);
const mode = args.find(arg => !arg.startsWith('--')) || 'production';
const watch = args.includes('--watch');

const buildOptions = {
  entryPoints: ['src/index.jsx'],
  bundle: true,
  outfile: 'dist/bundle.js',
  loader: { '.jsx': 'jsx' },
  jsx: 'automatic',
  define: {
    'process.env.NODE_ENV': JSON.stringify(mode),
  },
  logLevel: 'info',
};

if (watch) {
  const ctx = await esbuild.context(buildOptions);
  await ctx.watch();
  console.log(`[JARVIS] esbuild watching in ${mode} mode`);
  await new Promise(() => {});
} else {
  await esbuild.build(buildOptions);
}
