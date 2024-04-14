# homeassistant-infinitude-beyond

Home Assistant custom component for controlling Carrier Infinity Touch thermostats through an [Infinitude](https://github.com/nebulous/infinitude) proxy server.

This is an updated version of the [original Infinitude integration](https://github.com/MizterB/homeassistant-infinitude), which was developed back in 2019. Home Assistant has changed a lot since then, but the original integration has done the bare minimum to remain supported. This version aims to be compatible with modern HA standards, and hopefully address a number of longstanding issues along the way.

# Installation via HACS

This custom component can be integrated into [HACS](https://github.com/hacs/integration), so you can track future updates. If you have do not have have HACS installed, please see [their installation guide](https://hacs.xyz/docs/installation/manual).

1. Select HACS from the left-hand navigation menu.

2. Click _Integrations_.

3. Click the three dots in the upper right-hand corner and select _Custom Repositories_.

4. Paste "https://github.com/MizterB/homeassistant-infinitude-beyond" into _Repository_, select "Integration" as _Category_, and click Add.

5. Close the Custom repositories dialog after it updates with the new integration.

6. "Infinitude" will appear in your list of repositories. Click to open, click the following Download buttons.

# Configuration

Configuration is done via the UI. Add the "Infinitude Beyond" integration via the Integration settings, then provide the hostname/IP and port of your Infinitude server in the configuration dialog.

# Changelog

See [Releases](https://github.com/MizterB/homeassistant-infinitude-beyond/releases)
