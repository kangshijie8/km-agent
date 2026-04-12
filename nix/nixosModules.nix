{ config, lib, pkgs, ... }:

let
  cfg = config.services.kunming-agent;
  
  kunming-agent = pkgs.stdenv.mkDerivation {
    name = "kunming-agent";
    src = ../.;
    
    buildInputs = with pkgs; [
      python3
      python3Packages.pip
      python3Packages.virtualenv
    ];
    
    installPhase = ''
      mkdir -p $out/lib/kunming-agent
      cp -r . $out/lib/kunming-agent/
      
      mkdir -p $out/bin
      cat > $out/bin/km << 'EOF'
      #!/bin/sh
      cd $out/lib/kunming-agent
      exec ${pkgs.python3}/bin/python -m kunming "$@"
      EOF
      chmod +x $out/bin/km
    '';
  };
in
{
  options.services.kunming-agent = {
    enable = lib.mkEnableOption "Kunming Agent service";
    
    package = lib.mkOption {
      type = lib.types.package;
      default = kunming-agent;
      description = "The Kunming Agent package to use";
    };
    
    user = lib.mkOption {
      type = lib.types.str;
      default = "kunming";
      description = "User to run Kunming Agent as";
    };
    
    group = lib.mkOption {
      type = lib.types.str;
      default = "kunming";
      description = "Group to run Kunming Agent as";
    };
    
    home = lib.mkOption {
      type = lib.types.path;
      default = "/var/lib/kunming";
      description = "Home directory for Kunming Agent";
    };
    
    environment = lib.mkOption {
      type = lib.types.attrsOf lib.types.str;
      default = {};
      description = "Environment variables for Kunming Agent";
    };
    
    config = lib.mkOption {
      type = lib.types.attrs;
      default = {};
      description = "Kunming Agent configuration";
    };
  };
  
  config = lib.mkIf cfg.enable {
    users.users.${cfg.user} = {
      isSystemUser = true;
      group = cfg.group;
      home = cfg.home;
      createHome = true;
    };
    
    users.groups.${cfg.group} = {};
    
    systemd.services.kunming-agent = {
      description = "Kunming Agent";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      
      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        WorkingDirectory = cfg.home;
        ExecStart = "${cfg.package}/bin/km --daemon";
        Restart = "on-failure";
        RestartSec = 5;
        
        # Security hardening
        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        ReadWritePaths = [ cfg.home ];
      };
      
      environment = cfg.environment;
    };
    
    # Create config file if provided
    environment.etc."kunming/config.yaml" = lib.mkIf (cfg.config != {}) {
      text = builtins.toJSON cfg.config;
    };
  };
}
