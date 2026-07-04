import { spawn } from "node:child_process";
import { once } from "node:events";

/** @type {NodeJS.ProcessEnv} */
const environment = {
    ...process.env,
    PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1",
};
const python =
    typeof environment.PYTHON === "string" && environment.PYTHON.length > 0
        ? environment.PYTHON
        : "python";
const child = spawn(
    python,
    [
        "-m",
        "pytest",
        "-p",
        "pytest_cov",
        ...process.argv.slice(2),
    ],
    {
        env: environment,
        stdio: "inherit",
    }
);

const closeResult = /** @type {unknown[]} */ (await once(child, "close"));
const code = closeResult[0];

process.exitCode = typeof code === "number" ? code : 1;
