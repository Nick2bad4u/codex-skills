import { TSDocConfigFile } from "@microsoft/tsdoc-config";

const config = TSDocConfigFile.loadFile("tsdoc.json");
const messages = config.log.messages;

for (const message of messages) {
    console.error(message.toString());
}

if (messages.length > 0) {
    throw new Error("tsdoc.json validation failed");
}

console.log("Validated tsdoc.json");
