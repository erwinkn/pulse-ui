# Pulse


> [!WARNING]
> Pulse is currently very early and absolutely not production-ready. I am currently piloting it for internal usage. I do not recommend it using it for an application at this stage, as project support in the CLI is non-existent and you will likely encounter problems.

Pulse is a full-stack Python framework to build React applications. It aims to be the best way to build complex web applications from Python.

Pulse's guiding principles are:
- Straightforward code, it's "just Python". Pulse tries really hard to avoid surprises and magic.
- Performance. Your app should respond to user interactions as fast as the speed of light allows. Your dev workflow should be the same: fast starts and instant reloads.
- Extremely easy integration with the JavaScript and React ecosystems. Want to install a library and use its React components from Python? Want to add your own custom React components to your project? You got it. 

## Project structure

A Pulse project has two parts:
- The Pulse Python server, where most of your application is defined.
- The React application, using [Vite](https://vite.dev/) and [React Router](https://reactrouter.com/home). Pulse generates routes and runs the app for you, but you are free to modify and extend the project as you wish.

You can see an example in the `pulse-demo/` folder. Typically, a Pulse project contains the Python server at the top-level and the React application in a subfolder, named `pulse-web/` by default. This is not a prescription however, you can configure Pulse to have the React application anywhere you want it.

Pulse's CLI is currently limited to running the Pulse application, or just generating the Pulse routes in the React application. There are no utilities to help with project setup. If you want to use Pulse, you will need to install the `pulse-ui-client` package from NPM and the `pulse` Python package from Git, and imitate the setup in `pulse-demo/` yourself.
