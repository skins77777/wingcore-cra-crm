// SDK 2.41 Windows manifests used backslashes; Linux package lookup needs '/'.
// Scope this adaptation to the deployment CLI process; do not alter global Node.
import path from 'node:path';
import { syncBuiltinESMExports } from 'node:module';
const nativeRelative = path.relative;
path.relative = (from, to) => nativeRelative(from, to).replaceAll('\\', '/');
syncBuiltinESMExports();
