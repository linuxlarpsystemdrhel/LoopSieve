use serde_json::{Map, Value};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

fn read(path: &Path) -> Value {
    println!("cargo:rerun-if-changed={}", path.display());
    serde_json::from_slice(&fs::read(path).expect("read catalog manifest"))
        .unwrap_or_else(|error| panic!("invalid catalog manifest {}: {error}", path.display()))
}

fn main() {
    let root = Path::new("../../src/loopsieve/data");
    let mut catalog = Map::new();
    for group in ["agents", "skills", "technologies", "plugins"] {
        let folder = root.join(group);
        println!("cargo:rerun-if-changed={}", folder.display());
        let mut paths: Vec<_> = fs::read_dir(folder)
            .expect("read catalog folder")
            .map(|entry| entry.expect("read catalog entry").path())
            .filter(|path| {
                path.extension()
                    .is_some_and(|extension| extension == "json")
            })
            .collect();
        paths.sort();
        catalog.insert(
            group.into(),
            Value::Array(paths.iter().map(|path| read(path)).collect()),
        );
    }
    for (name, path) in [
        ("providers", "providers/catalog.json"),
        ("innovations", "innovations.json"),
        ("models", "models/catalog.json"),
    ] {
        catalog.insert(name.into(), read(&root.join(path)));
    }
    let destination =
        PathBuf::from(env::var_os("OUT_DIR").expect("Cargo OUT_DIR")).join("catalog.json");
    fs::write(
        destination,
        serde_json::to_vec(&catalog).expect("encode native catalog"),
    )
    .expect("write native catalog");
}
