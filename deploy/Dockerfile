# 生产镜像：零运行时依赖，直接跑 TypeScript（Node 24 类型擦除）。
FROM node:24-bookworm-slim

WORKDIR /app
COPY package.json tsconfig.json ./
COPY src ./src
COPY scripts ./scripts

RUN mkdir -p /data /work /config && chown -R node:node /app /data /work
USER node

ENV NODE_ENV=production
EXPOSE 4780 64735

ENTRYPOINT ["node", "--no-warnings", "src/cli.ts"]
CMD ["run", "/config/seed.config.json"]