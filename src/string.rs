use std::io;

fn main() {
    println!("Guess the number!");
    println!("Please input your guess.");

    let mut guess = String::new(); 
    // the :: indicates a function associated to a type
    // which we capitalize in order to signify it.

    // an associated function is one that's implemented on a type
    // what does an 'empty' string mean?
    // the function above returns a empty growable UTF-8 string


    io::stdin()
        .read_line(&mut guess)
        .expect("Failed to read line");

    // the first line returns a 'handle' Stdin which is a global buffer for holding the std input
    // read_line then grabs one line from the buffer, and copies it to (the address of) `guess`
    // read_line also return something organized as an enum, with the 'result' type.
    // the `Result` type has a `expect` method defined for it
    println!("You guessed: {guess}");

}