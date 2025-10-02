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

## Styling with CSS modules

Pulse ships `ps.css_module()` to co-locate Mantine- or React-style CSS modules with the Python components that use them. The helper resolves paths relative to the file where it is called, copies the module into the generated web bundle, and exposes its classes as attribute accessors:

```python
import pulse as ps

styles = ps.css_module("./button.module.css", relative=True)

def View():
    return ps.button(className=styles.primary)["Click me"]
```

Behind the scenes Pulse imports the CSS module in the generated route file and wires it through the renderer so `className` receives the compiled class string. Pass `relative=True` to resolve paths next to the calling module; otherwise the path is treated like a regular `Path`. Modules can live anywhere in your project tree—the code generator copies them into `pulse/css/` with unique filenames. CSS references are tracked similarly to callbacks, so the values cannot be forged or misused from user code. For side-effect stylesheets (like `@mantine/core/styles.css`), call `ps.css("@mantine/core/styles.css")`; Pulse will emit an `import` for you during codegen (and copy local files when needed).

```python
ps.css("@mantine/core/styles.css")  # side-effect import
```
