<?php
ini_set('log_errors', '1');
ini_set('error_log', '/srv/personal_website/logs/app.log');

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

function log_err(string $context, string $message): void {
    $line = date('Y-m-d H:i:s') . " [$context] $message" . PHP_EOL;
    file_put_contents('/srv/personal_website/logs/app.log', $line, FILE_APPEND);
}

$db_path = '/var/data/site.db';
$uri = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$uri = rtrim(preg_replace('#^/api#', '', $uri), '/');

function db(): PDO {
    global $db_path;
    static $pdo;
    if (!$pdo) {
        $pdo = new PDO("sqlite:$db_path");
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $pdo->exec("CREATE TABLE IF NOT EXISTS posts (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            title   TEXT NOT NULL,
            slug    TEXT NOT NULL UNIQUE,
            tag     TEXT,
            body    TEXT,
            created TEXT NOT NULL DEFAULT (date('now'))
        )");
    }
    return $pdo;
}

function json_out($data, int $status = 200): void {
    http_response_code($status);
    echo json_encode($data);
    exit;
}

// GET /api/posts
if ($uri === '/posts' && $_SERVER['REQUEST_METHOD'] === 'GET') {
    $rows = db()->query("SELECT id, title, slug, tag, created FROM posts ORDER BY created DESC")->fetchAll(PDO::FETCH_ASSOC);
    json_out($rows);
}

// GET /api/posts/{id}
if (preg_match('#^/posts/(\d+)$#', $uri, $m) && $_SERVER['REQUEST_METHOD'] === 'GET') {
    $stmt = db()->prepare("SELECT * FROM posts WHERE id = ?");
    $stmt->execute([$m[1]]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);
    $row ? json_out($row) : json_out(['error' => 'not found'], 404);
}

// GET /api/markets
if ($uri === '/markets' && $_SERVER['REQUEST_METHOD'] === 'GET') {
    $script = '/srv/personal_website/integrations/src/markets.py';
    $python = '/srv/personal_website/integrations/.venv/bin/python';
    $output = shell_exec(escapeshellcmd("$python $script") . ' 2>&1');
    $data = json_decode($output, true);
    if ($data !== null) {
        json_out($data);
    } else {
        log_err('markets', "Python script failed: $output");
        json_out(['error' => 'failed to fetch market data'], 502);
    }
}

// GET /api/health
if ($uri === '' || $uri === '/health') {
    json_out(['status' => 'ok']);
}

json_out(['error' => 'not found'], 404);
