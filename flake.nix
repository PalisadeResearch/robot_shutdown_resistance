{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            # Basics
            git
            ninja
            # Python
            uv
            # Typesetting
            typst
            texlive.combined.scheme-medium
            noto-fonts-color-emoji
            newcomputermodern
            fontconfig
            # Nix
            nil
            nixfmt-rfc-style
            # JavaScript
            nodejs # remote-mcp
          ];
          shellHook = ''
            export TYPST_FONT_PATHS="${pkgs.noto-fonts-color-emoji}:${pkgs.newcomputermodern}"
            export FONTCONFIG_FILE="${
              pkgs.makeFontsConf {
                fontDirectories = [
                  pkgs.newcomputermodern
                  pkgs.noto-fonts-color-emoji
                ];
              }
            }"
          '';
        };
      }
    );
}
