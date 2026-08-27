import { init, getAuthToken } from "@heyputer/puter.js/src/init.cjs";

async function testAI() {
    try {
        console.log("Opening browser window for Puter authentication...");

        // 1. Automatically prompts browser sign-in and captures the token
        const authToken = await getAuthToken();

        // 2. Initializes the app with the verified token
        const puter = init(authToken);

        console.log("Authentication successful! Testing AI chat...");
        const response = await puter.ai.chat("Hello! Say 'Puter is ready'.");

        // 3. Print the text payload response safely
        console.log("Response:", response.message?.content?.toString() || response);
    } catch (error) {
        console.error("Error running Puter:", error);
    }
}

testAI();