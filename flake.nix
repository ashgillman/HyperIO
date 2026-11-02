{
  description = "HyperIO development environment and desktop applications";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { nixpkgs, ... }:
    let
      systems = [ "aarch64-darwin" "x86_64-darwin" "aarch64-linux" "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          unlzw3 = pkgs.python3Packages.buildPythonPackage {
            pname = "unlzw3";
            version = "0.2.3";
            pyproject = true;
            src = pkgs.fetchPypi {
              pname = "unlzw3";
              version = "0.2.3";
              hash = "sha256-7eXZKMeS//naQG8gM0+XOWkzJ/RI84OuHfF3RicZe7s=";
            };
            build-system = [ pkgs.python3Packages.setuptools pkgs.python3Packages.wheel ];
            pythonImportsCheck = [ "unlzw3" ];
          };
          python = pkgs.python3.withPackages (ps: with ps; [
            tkinter
            numpy
            scipy
            shapely
            unlzw3
            openpyxl
            pydicom
            pytest
          ]);
        in
        {
          default = pkgs.mkShell {
            packages = [ python ];
            shellHook = ''
              export PYTHONPATH="$PWD/src''${PYTHONPATH:+:$PYTHONPATH}"
            '';
          };
        });
    };
}
