/** 组合信道：按地址前缀把消息路由到对应渠道（gh: / fs: / 其它）。 */
export class CompositeChannel {
    routes;
    constructor(routes) {
        this.routes = routes;
    }
    async send(channel, text) {
        const route = this.routes.find((item) => channel.address.startsWith(item.prefix));
        if (!route)
            throw new Error(`no channel route for address: ${channel.address}`);
        await route.writer.send(channel, text);
    }
}
//# sourceMappingURL=composite.js.map